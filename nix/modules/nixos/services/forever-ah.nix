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

    # blizz publishes th us forever dumps at ~:13 every hour (seen 2026-11-09), so grab them fresh
    systemd.timers.forever-ah-scrape = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "*-*-* *:20:00";
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
        # means a new build restarts this unit on switch, so code changes go live without waiting 4 :20
        ExecStartPre = pkgs.writeShellScript "forever-gold-site" ''
          set -euo pipefail
          mkdir -p ${www}
          rm -rf ${www}/assets ${www}/index.html ${www}/nyan.gif
          cp -rT --no-preserve=mode ${pkgs.rv32ima.forever-ah-site} ${www}
        '';
        ExecStart = "${lib.getExe pkgs.static-web-server} --host 127.0.0.1 --port ${toString port} --root ${www}";
        Restart = "on-failure";
      };
    };
    rv32ima.machine.tailscale.services.forever-gold = {
      inherit port;
    };

    # 4 poking at it over ssh: FOREVER_AH_DB is already set, so just `forever-ah analyze`
    environment.systemPackages = [ pkgs.rv32ima.forever-ah ];
    environment.variables.FOREVER_AH_DB = db;
  };
}
