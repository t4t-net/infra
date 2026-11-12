{
  config,
  lib,
  pkgs,
  ...
}:
let
  state = "/var/lib/forever-ah";
  db = "${state}/forever-ah.sqlite";
  www = "${state}/www";
  port = 8471;

  forever-ah = "${lib.getExe pkgs.rv32ima.forever-ah} --db ${db}";

  # th ForeverScan addon's SavedVariables, pushed from ellie's gaming pc. th inbox isnt state: if it's wiped
  # th pc just sends th file again next time it changes
  inbox = "/var/lib/forever-ah-inbox";
  # generated on desktop-kdblba8 (2026-11-11), private half never left it
  foreverScanKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOAjP3Jprli7zWzo6zF5+oYBlbHrgo0pv+oAUpGbdOoJ forever-scan@desktop-kdblba8";
  # th only thing th pc's key can do: drop one file in th inbox. capped, written aside nd renamed into
  # place so th import never reads half an upload
  ingest = pkgs.writeShellApplication {
    name = "forever-ah-ingest";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      max=$((64 * 1024 * 1024))
      tmp=$(mktemp ${inbox}/.upload.XXXXXX)
      trap 'rm -f "$tmp"' EXIT
      head -c $((max + 1)) > "$tmp"
      size=$(stat -c %s "$tmp")
      if [ "$size" -gt "$max" ] || [ "$size" -eq 0 ]; then
        echo "$size bytes, not taking it (want 1 2 $max)" >&2
        exit 1
      fi
      chmod 0644 "$tmp"
      mv "$tmp" ${inbox}/ForeverScan.lua
      trap - EXIT
      echo "got $size bytes"
    '';
  };

  # sws's default sends max-age=86400 on index.html, so browsers kept a day-old page pointing at
  # an old bundle. html nd json change every deploy/hour; vite's hashed assets never change
  swsConfig = (pkgs.formats.toml { }).generate "forever-gold-sws.toml" {
    general = {
      host = "127.0.0.1";
      inherit port;
      root = www;
      cache-control-headers = false;
    };
    advanced.headers = [
      {
        source = "**/*.{html,json}";
        headers.Cache-Control = "no-cache";
      }
      {
        source = "**/assets/**";
        headers.Cache-Control = "public, max-age=31536000, immutable";
      }
    ];
  };

  # every unit runs as th same dynamic user so they can share th 0700 state dir
  sandbox = {
    DynamicUser = true;
    User = "forever-ah";
    StateDirectory = "forever-ah";
    StateDirectoryMode = "0700";
    UMask = "0077";
    ProtectHome = true;
    PrivateDevices = true;
    CapabilityBoundingSet = "";
    RestrictAddressFamilies = [
      "AF_INET"
      "AF_INET6"
    ];
  };

  job = description: commands: {
    inherit description;
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    environment = {
      # progress lines otherwise sit in python's buffer until exit nd th journal looks frozen
      PYTHONUNBUFFERED = "1";
      # client db2 tables come off blizzard's CDN; ~300mb of archive indexes th first time, reused after
      FOREVER_AH_CDN_CACHE = "${state}/cdn-cache";
    };
    serviceConfig = sandbox // {
      Type = "oneshot";
      ExecStart = map (c: "${forever-ah} ${c}") commands;
      EnvironmentFile = config.sops.templates."forever-ah/env".path;
    };
  };
in
{
  config = {
    sops.secrets = lib.genAttrs [ "forever-ah/client_id" "forever-ah/client_secret" "forever-ah/discord_webhook" ] (name: {
      sopsFile = ../../../machines/nixos/psychoboost/secrets/forever-ah.yaml;
      key = lib.removePrefix "forever-ah/" name;
    });

    sops.templates."forever-ah/env".content = ''
      BNET_CLIENT_ID=${config.sops.placeholder."forever-ah/client_id"}
      BNET_CLIENT_SECRET=${config.sops.placeholder."forever-ah/client_secret"}
    '';

    # each scrape rewrites data.json, so th page is never more than an hour behind blizz, then
    # pings discord about any flip tht just opened
    systemd.services.forever-ah-scrape = lib.recursiveUpdate (job "snapshot every wow forever auction house" [
      "scrape"
      "export --out ${www}/data.json"
      "alert --data ${www}/data.json --state ${state}/alert-state.json --webhook-file %d/discord-webhook --site https://forever-gold.tail09d5b.ts.net/"
    ]) {
      # th dynamic user cant read a root-owned sops file, so systemd hands this unit its own copy
      serviceConfig.LoadCredential = [ "discord-webhook:${config.sops.secrets."forever-ah/discord_webhook".path}" ];
    };
    # ~4k static api calls 4 all eight professions plus SkillLineAbility off th CDN 4 spell ids nd
    # skill ranges. recipes barely change so weekly is plenty.
    # th scrape's raw-auction watchlist comes from these, so kick it by hand on a fresh db
    # quests: questie's forever db (~4mb of lua off github) + every quest's rewards from th api (~7k calls)
    systemd.services.forever-ah-recipes = job "cache wow forever recipes nd quests" [
      "recipes"
      "quests"
    ];

    # blizz's us forever dumps carry Last-Modified ~:22:43 every hour (17:22:43, 18:22:43, 19:22:43 on
    # 2026-11-11; it was ~:13 on 11-09). at :20 we fetched 3 min early nd always got th PREVIOUS hour's dump, so
    # th site ran an hour stale: a rerun at 21:02 got 20:22:44 where th 20:20 run got 19:22:43. :30 leaves margin
    systemd.timers.forever-ah-scrape = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "*-*-* *:30:00";
        RandomizedDelaySec = "2m";
        Persistent = true;
      };
    };
    systemd.timers.forever-ah-recipes = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "weekly";
        RandomizedDelaySec = "1h";
        Persistent = true;
      };
    };

    # th gold meta page, loopback only; tailscale serve is th way in
    systemd.services.forever-gold = {
      description = "wow forever gold meta site";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = sandbox // {
        # th site comes from th store, data.json from th hourly export. naming th site's store path here
        # means a new build restarts this unit on switch, so code changes go live without waiting 4 :30
        ExecStartPre = pkgs.writeShellScript "forever-gold-site" ''
          set -euo pipefail
          mkdir -p ${www}
          rm -rf ${www}/assets ${www}/index.html ${www}/nyan.gif
          cp -rT --no-preserve=mode ${pkgs.rv32ima.forever-ah-site} ${www}
        '';
        ExecStart = "${lib.getExe pkgs.static-web-server} --config-file ${swsConfig}";
        Restart = "on-failure";
      };
    };
    rv32ima.machine.tailscale.services.forever-gold = {
      inherit port;
    };

    # th gaming pc ships ForeverScan.lua here w `ssh forever-ingest@psychoboost < file`. a plain key, not a
    # ca cert: certs expire fast, so th pc wud need a credential tht can mint them, nd its th least trusted
    # box around (third-party addons nd launchers). this key can only ever run ingest
    users.users.forever-ingest = {
      isSystemUser = true;
      group = "forever-ingest";
      # forced commands still go through th login shell's -c, nologin wud refuse them
      shell = pkgs.bashInteractive;
      openssh.authorizedKeys.keys = [
        ''restrict,command="${lib.getExe ingest}" ${foreverScanKey}''
      ];
    };
    users.groups.forever-ingest = { };
    systemd.tmpfiles.rules = [ "d ${inbox} 0755 forever-ingest forever-ingest -" ];

    # a fresh upload gets imported nd th site re-exported right away, so "live" on th page means live
    systemd.paths.forever-ah-addon-import = {
      wantedBy = [ "paths.target" ];
      pathConfig.PathChanged = "${inbox}/ForeverScan.lua";
    };
    systemd.services.forever-ah-addon-import = job "import th ForeverScan addon's dumps nd watch polls" [
      "addon-import ${inbox}/ForeverScan.lua --house 111"
      "export --out ${www}/data.json"
    ];

    # 4 poking at it over ssh: FOREVER_AH_DB is already set, so just `forever-ah analyze`
    environment.systemPackages = [ pkgs.rv32ima.forever-ah ];
    environment.variables.FOREVER_AH_DB = db;
  };
}
