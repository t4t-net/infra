{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
let
  cfg = config.rv32ima.services.soularr;
in
{
  options.rv32ima.services.soularr = {
    package = mkPackageOption pkgs.rv32ima "soularr" { };

    port = mkOption {
      type = types.port;
      default = 8265;
      description = "The port to listen on";
    };

    config = mkOption {
      type = lib.types.anything;
    };

    dataDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/soularr";
      description = "The directory where Soularr stores its data files.";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "lidarr";
      description = "User account under which Radarr runs.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "lidarr";
      description = "Group under which Radarr runs.";
    };
  };

  config =
    let
      customToINI = generators.toINI {
        mkKeyValue = generators.mkKeyValueDefault { } "=";
      };
      renderedConfig = customToINI cfg.config;
    in
    {
      rv32ima.machine.impermanence.extraPersistDirectories = [
        {
          path = /var/lib/soularr;
          mode = "0700";
          owner = "${cfg.user}";
          group = "${cfg.group}";
        }
      ];

      sops.secrets."services/soularr/lidarr-api-key" = {
        sopsFile = ./secrets.yaml;
      };

      sops.secrets."services/soularr/soulseek-api-key" = {
        sopsFile = ./secrets.yaml;
      };

      rv32ima.services.soularr.config = {
        "Download Settings" = {
          download_filtering = "True";
          extensions_whitelist = "lrc,nfo,txt";
          use_extension_whitelist = "False";
        };
        Lidarr = {
          api_key = "${config.sops.placeholder."services/soularr/lidarr-api-key"}";
          disable_sync = "False";
          download_dir = "/media/downloads/slskd/complete";
          host_url = "http://localhost:8686";
        };
        Logging = {
          backup_count = "3";
          datefmt = "%Y-%m-%dT%H:%M:%S%z";
          format = "[%(levelname)s|%(module)s|L%(lineno)d] %(asctime)s: %(message)s";
          level = "INFO";
          log_file = "soularr.log";
          log_to_file = "True";
          max_bytes = "1048576";
        };
        "Release Settings" = {
          accepted_countries = "Europe,Japan,United Kingdom,United States,[Worldwide],Australia,Canada";
          accepted_formats = "CD,Digital Media,Vinyl";
          allow_multi_disc = "True";
          skip_region_check = "True";
          use_most_common_tracknum = "True";
          use_selected_lidarr_release = "False";
        };
        "Search Settings" = {
          album_prepend_artist = "True";
          allowed_filetypes = "flac,wav,mp3,m4a";
          failed_import_denylist = "True";
          ignored_users = "uniqueslskd7";
          maximum_peer_queue = "50";
          minimum_filename_match_ratio = "0.5";
          minimum_peer_upload_speed = 1000000;
          minimum_search_interval = "5";
          number_of_albums_to_grab = "10";
          search_blacklist = "";
          search_source = "missing";
          search_timeout = "5000";
          search_type = "incrementing_page";
          title_blacklist = "";
        };
        Slskd = {
          api_key = "${config.sops.placeholder."services/soularr/soulseek-api-key"}";
          delete_searches = "False";
          download_dir = "/media/downloads/slskd/complete";
          host_url = "http://localhost:5030";
          remote_queue_timeout = "300";
          stalled_timeout = "3600";
          url_base = "/";
        };
      };

      rv32ima.machine.tailscale.services.soularr = {
        targetUnit = "soularr-web-ui.service";
        port = 8265;
      };

      sops.templates."services/soularr/config/config.ini" = {
        content = renderedConfig;
        owner = "${cfg.user}";
        group = "${cfg.group}";
      };

      systemd.tmpfiles.settings."10-soularr".${cfg.dataDir}.d = {
        inherit (cfg) user group;
        mode = "0700";
      };

      systemd.timers.soularr = {
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "30s";
          OnUnitActiveSec = "60s";
        };
      };

      systemd.services.soularr = {
        after = [
          "network.target"
          "slskd.service"
        ];

        script = ''
          cp ${config.sops.templates."services/soularr/config/config.ini".path} ${cfg.dataDir}/config.ini
          ${cfg.package}/bin/soularr -c ${cfg.dataDir} -v ${cfg.dataDir}
        '';

        serviceConfig = {
          Type = "oneshot";
          User = cfg.user;
          Group = cfg.group;

          # Hardening
          CapabilityBoundingSet = "";
          NoNewPrivileges = true;
          ProtectHome = true;
          ProtectClock = true;
          ProtectKernelLogs = true;
          PrivateTmp = true;
          PrivateDevices = true;
          PrivateUsers = true;
          ProtectKernelTunables = true;
          ProtectKernelModules = true;
          ProtectControlGroups = true;
          RestrictSUIDSGID = true;
          RemoveIPC = true;
          UMask = "0002";
          ProtectHostname = true;
          ProtectProc = "invisible";
          RestrictAddressFamilies = [
            "AF_INET"
            "AF_INET6"
            "AF_UNIX"
          ];
          RestrictNamespaces = true;
          RestrictRealtime = true;
          LockPersonality = true;
          SystemCallArchitectures = "native";
          SystemCallFilter = [
            "@system-service"
            "~@privileged"
            "~@debug"
            "~@mount"
            "@chown"
          ];
        };
      };

      systemd.services.soularr-web-ui = {
        wantedBy = [ "multi-user.target" ];
        after = [ "soularr.service" ];

        script = ''
          ${cfg.package}/bin/soularr-webui --var-dir ${cfg.dataDir} --port ${toString cfg.port}
        '';

        serviceConfig = {
          Type = "simple";
          User = cfg.user;
          Group = cfg.group;
          Restart = "on-failure";

          # Hardening
          CapabilityBoundingSet = "";
          NoNewPrivileges = true;
          ProtectHome = true;
          ProtectClock = true;
          ProtectKernelLogs = true;
          PrivateTmp = true;
          PrivateDevices = true;
          PrivateUsers = true;
          ProtectKernelTunables = true;
          ProtectKernelModules = true;
          ProtectControlGroups = true;
          RestrictSUIDSGID = true;
          RemoveIPC = true;
          UMask = "0002";
          ProtectHostname = true;
          ProtectProc = "invisible";
          RestrictAddressFamilies = [
            "AF_INET"
            "AF_INET6"
            "AF_UNIX"
          ];
          RestrictNamespaces = true;
          RestrictRealtime = true;
          LockPersonality = true;
          SystemCallArchitectures = "native";
          SystemCallFilter = [
            "@system-service"
            "~@privileged"
            "~@debug"
            "~@mount"
            "@chown"
          ];
        };
      };

      users.users = lib.mkIf (cfg.user == "soularr") {
        soularr = {
          inherit (cfg) group;
          isSystemUser = true;
          home = cfg.dataDir;
        };
      };

      users.groups = lib.mkIf (cfg.group == "soularr") {
        soularr = { };
      };
    };
}
