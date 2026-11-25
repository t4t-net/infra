{
  config,
  lib,
  pkgs,
  ...
}:

# zoomies: a tiny ci tht builds infra's main, uploads it 2 cache.t4t.net nd publishes
# latest/<job>.json 4 th fleet. see nix/packages/zoomies/DESIGN.md 4 th contract
let
  cfg = config.rv32ima.services.zoomies;
  stateDir = "/var/lib/zoomies";
  publicDir = "${stateDir}/public";

  configFile = pkgs.writeText "zoomies.json" (
    builtins.toJSON {
      repo = "https://github.com/t4t-net/infra";
      branch = "main";
      flake_dir = "nix";
      flake_attr = "hydraJobs";
      state_dir = stateDir;
      # same bucket, key nd settings as hydra's store_uri, so during cutover both upload identical
      # signed paths nd it doesnt matter which one got there first
      store_uri = "s3://rv32ima-nix-store?secret-key=${
        config.sops.secrets."zoomies/nix-signing-key".path
      }&endpoint=359f72dd5610ef51b6f186e0818ab188.r2.cloudflarestorage.com&region=auto&compression=zstd";
      # same as hydra: 4 x 4G fits in wat th nix-daemon's MemoryHigh leaves over
      eval_workers = 4;
      eval_max_memory_mb = 4096;
      discord_webhook_file =
        if cfg.discord.enable then config.sops.secrets."zoomies/discord-webhook".path else null;
      public_url = cfg.publicUrl;
      keep_runs = 50;
    }
  );
in
{
  options.rv32ima.services.zoomies = {
    enable = lib.mkEnableOption "zoomies, th tiny ci tht replaces hydra";

    package = lib.mkPackageOption pkgs.rv32ima "zoomies" { pkgsText = "pkgs.rv32ima"; };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8472;
      description = "Loopback port nginx serves the public dir on; tailscale serve is the way in.";
    };

    interval = lib.mkOption {
      type = lib.types.str;
      default = "2min";
      description = "How long to wait after a tick finishes before polling main again (systemd time span).";
    };

    publicUrl = lib.mkOption {
      type = lib.types.str;
      default = "https://zoomies.tail09d5b.ts.net";
      description = "Where the public dir ends up, used for links in discord pings.";
    };

    discord.enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Ping discord once per run, using the fleet's hydra-deploy webhook.";
    };
  };

  config = lib.mkIf cfg.enable {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/zoomies;
        mode = "0750";
        owner = "zoomies";
        group = "zoomies";
      }
    ];

    users.users.zoomies = {
      isSystemUser = true;
      group = "zoomies";
      # git nd nix both want a writable $HOME 4 their caches
      home = stateDir;
    };
    users.groups.zoomies = { };
    # nginx only gets group read on th state dir. state/ nd gcroots/ r just ids, shas nd symlinks,
    # th secrets live in /run/secrets nd nginx's root is public/ anyway
    users.users.${config.services.nginx.user}.extraGroups = [ "zoomies" ];

    # without impermanence nobody else makes these, nd nginx shud have a root b4 th first run
    systemd.tmpfiles.rules = [
      "d ${stateDir} 0750 zoomies zoomies -"
      "d ${publicDir} 0750 zoomies zoomies -"
    ];

    # th same secrets hydra uses, under their own names so zoomies can own its copies. th signing key
    # is wat makes cache.t4t.net trust th paths, so its only readable by zoomies
    sops.secrets."zoomies/r2" = {
      sopsFile = ./hydra/secrets.yaml;
      key = "services/hydra/r2";
      owner = "zoomies";
      group = "zoomies";
    };
    sops.secrets."zoomies/nix-signing-key" = {
      sopsFile = ./hydra/secrets.yaml;
      key = "services/hydra/nix-signing-key";
      owner = "zoomies";
      group = "zoomies";
    };
    sops.secrets."zoomies/discord-webhook" = lib.mkIf cfg.discord.enable {
      sopsFile = ../../../secrets/hydra-deploy.yaml;
      key = "discord-webhook";
      owner = "zoomies";
      group = "zoomies";
    };

    # no nix.settings.trusted-users: building drvs, `nix copy` out of th local store (th signing
    # happens client side w th key in store_uri) nd indirect gc roots all work 4 plain users.
    # trusted wud make a bug in zoomies root on th box, hydra-queue-runner only needs it 4 its own
    # remote builder protocol
    systemd.services.zoomies = {
      description = "build infra's main nd publish it 4 th fleet";
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      # a deploy of psychoboost itself shudnt kill a run halfway thru its builds. th next tick
      # picks up th new unit
      restartIfChanged = false;
      path = [
        config.nix.package
        pkgs.git
        pkgs.nix-eval-jobs
      ];
      environment = {
        # progress lines otherwise sit in python's buffer until exit nd th journal looks frozen
        PYTHONUNBUFFERED = "1";
        XDG_CACHE_HOME = "/var/cache/zoomies";
      };
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${lib.getExe cfg.package} run --config ${configFile}";
        # AWS_* 4 th s3 store
        EnvironmentFile = config.sops.secrets."zoomies/r2".path;
        User = "zoomies";
        Group = "zoomies";
        # th flake fetcher cache. fine 2 lose on reboot
        CacheDirectory = "zoomies";
        # group read 4 nginx, nothing 4 anyone else
        UMask = "0027";

        # /nix stays reachable (ProtectSystem=full leaves it alone) cuz everything goes thru th
        # daemon socket, nd no PrivateNetwork cuz of github nd R2
        ProtectSystem = "full";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        RestrictSUIDSGID = true;
        RestrictRealtime = true;
        RestrictNamespaces = true;
        LockPersonality = true;
        SystemCallArchitectures = "native";
        RestrictAddressFamilies = [
          "AF_UNIX"
          "AF_INET"
          "AF_INET6"
        ];
      };
    };

    # inactive nd not active: a build can take way longer than 2 min, nd this way th next poll is
    # always a full interval after th last run ended instead of piling up behind it
    systemd.timers.zoomies = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "2min";
        OnUnitInactiveSec = cfg.interval;
      };
    };

    # only public/ is served, as plain static files. loopback only; tailscale serve is th way in
    services.nginx = {
      enable = true;
      virtualHosts.zoomies = {
        listen = [
          {
            addr = "127.0.0.1";
            inherit (cfg) port;
          }
        ];
        root = publicDir;
        extraConfig = ''
          autoindex off;
        '';
        # th agent polls these every 2 min, a cached one is a deploy tht shows up late
        locations."/latest/".extraConfig = ''
          default_type application/json;
          add_header Cache-Control "no-cache";
        '';
        # run.json changes while a run is going. .log isnt in nginx's mime.types nd wud download
        locations."/runs/".extraConfig = ''
          types {
            text/html html;
            application/json json;
            text/plain log;
          }
          add_header Cache-Control "max-age=10";
        '';
      };
    };

    rv32ima.machine.tailscale.services.zoomies = {
      inherit (cfg) port;
      # zoomies.service is a oneshot thts inactive most of th time, th serve unit wud go down w it
      targetUnit = "nginx.service";
    };
  };
}
