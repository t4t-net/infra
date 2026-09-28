{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.rv32ima.machine.backup;

  secretOpts = {
    sopsFile = cfg.secretsFile;
    owner = config.users.users."restic".name;
    group = config.users.users."restic".group;
    mode = "0440";
  };

  secretPath = name: config.sops.secrets.${name}.path;

  rcloneConfig = config.sops.templates."services/restic/rclone.conf".path;

  # ssh-keyscan fm2606.rsync.net
  knownHosts = pkgs.writeText "rsync.net-known_hosts" ''
    fm2606.rsync.net ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBNKxjzXzYdLwYoXcT/lRlxNzfHdGkr0pZDLk1tiPvLnbec1st3UjYq8HgYE1c/ko0VqINCR1uarlObpKpmazVHc=
    fm2606.rsync.net ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDOwRjdiftdinM0M8PNWnqU5Xbm8jTsljoTC6sHRoZ49UEm5C+gN3xnG9oTLoQJIwXjtMvTApjayuwuOQ7Sfu6S0FUuPos6fl7gigPRKqHjqkyLGTFXQ+2cZdYzDPnO1irEfvlfJB7tF92T7L3Lomun1WZBqXh0HB0P7ymCre75LAVpviVy4LP3S+SOwa5dYjFwTvUmwd7rw+f332/ojPDueuaSGFMfD0b6F8HWPUBbhkaS3f/b1dWqp35FS0AHkHWG38AY9TA9UXz3K762UE+HvVi6hj2ORO1+YoCjjXiWWDmCsTpbYBtyt6dVcfT639AVTkD1fqfq3n654VzYQ/Xr
    fm2606.rsync.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINdUkGe6kKn5ssz4WRZKjcws0InbQqZayenzk9obmP1z
  '';
in
{
  options = {
    rv32ima.machine.backup.enable = lib.mkEnableOption "restic backups";

    rv32ima.machine.backup.secretsFile = lib.mkOption {
      type = lib.types.path;
      description = "sops file holding the rclone secrets and each directory's restic password";
    };

    rv32ima.machine.backup.repositoryBase = lib.mkOption {
      type = lib.types.str;
      default = "rclone:secret:restic/${config.networking.hostName}";
      description = "prefix for every repository on this host; each directory gets <repositoryBase>/<name>";
    };

    rv32ima.machine.backup.pruneOpts = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "--keep-daily 7"
        "--keep-weekly 4"
        "--keep-monthly 6"
        "--max-unused 10%"
      ];
      description = "retention policy for every directory on this host; `forget --prune` runs after each backup";
    };

    rv32ima.machine.backup.metrics.directory = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "which directory's repository the restic prometheus exporter watches (it only supports one)";
    };

    rv32ima.machine.backup.directories = lib.mkOption {
      type = lib.types.attrsOf (
        lib.types.submodule (
          { config, name, ... }:
          {
            options = {
              path = lib.mkOption {
                type = lib.types.str;
              };
              repository = lib.mkOption {
                type = lib.types.str;
                default = "${cfg.repositoryBase}/${name}";
              };
              passwordSecret = lib.mkOption {
                type = lib.types.str;
                default = "services/restic/${name}/password";
              };
              pruneOpts = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = cfg.pruneOpts;
              };
              extraConfig = lib.mkOption {
                type = lib.types.attrs;
                default = { };
                description = "extra options merged into services.restic.backups.<name> (timerConfig, exclude, ...)";
              };
            };
          }
        )
      );
      default = { };
    };

    rv32ima.machine.backup.persist.enable =
      lib.mkEnableOption "backing up /persist to its own repository";

    rv32ima.machine.backup.persist.zfsDataset = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default =
        let
          fs = config.fileSystems."/persist" or null;
        in
        if fs != null && fs.fsType == "zfs" then fs.device else null;
      description = "dataset to snapshot so the backup sees a consistent /persist; null backs up /persist live";
    };

    rv32ima.machine.backup.persist.exclude = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "var/log"
        "var/lib/systemd/coredump"
        "var/lib/plex/Plex Media Server/Cache"
      ];
      description = "paths relative to /persist to leave out";
    };
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        assertions = [
          {
            assertion = cfg.metrics.directory == null || cfg.directories ? ${cfg.metrics.directory};
            message = "rv32ima.machine.backup.metrics.directory must name one of rv32ima.machine.backup.directories";
          }
        ];

        users.users."restic" = {
          enable = true;
          group = "restic";
          isSystemUser = true;
        };

        users.groups."restic".members = [
          "restic"
        ]
        ++ lib.optional (cfg.metrics.directory != null) "restic-exporter";

        sops.secrets = {
          # crypt passwords are rclone-obscured, same as they'd appear in a hand-written rclone.conf
          "services/restic/rclone/password" = secretOpts;
          "services/restic/rclone/password2" = secretOpts;
          "services/restic/rclone/sshKey" = secretOpts;
        }
        // lib.concatMapAttrs (_: dir: { ${dir.passwordSecret} = secretOpts; }) cfg.directories;

        sops.templates."services/restic/rclone.conf" = {
          inherit (secretOpts) owner group mode;
          content = ''
            [secret]
            type = crypt
            remote = chunker:
            password = ${config.sops.placeholder."services/restic/rclone/password"}
            password2 = ${config.sops.placeholder."services/restic/rclone/password2"}

            [chunker]
            type = chunker
            remote = rsync:.
            chunk_size = 1Gi

            [rsync]
            type = sftp
            host = fm2606.rsync.net
            user = fm2606
            key_file = ${secretPath "services/restic/rclone/sshKey"}
            known_hosts_file = ${knownHosts}
            shell_type = unix
            md5sum_command = md5 -r
            sha1sum_command = sha1 -r
          '';
        };

        services.restic.backups = lib.mapAttrs (
          _: dir:
          {
            inherit (dir) repository pruneOpts;
            user = config.users.users."restic".name;
            paths = [ dir.path ];
            passwordFile = secretPath dir.passwordSecret;
            rcloneConfigFile = rcloneConfig;
          }
          // dir.extraConfig
        ) cfg.directories;

        # the rclone config is only readable by restic, so run this as `sudo -u restic rclone-backup ...`
        environment.systemPackages = [
          (pkgs.writeShellScriptBin "rclone-backup" ''
            export RCLONE_CONFIG=${rcloneConfig}
            exec ${lib.getExe pkgs.rclone} "$@"
          '')
        ];

        services.prometheus.exporters.restic = lib.mkIf (cfg.metrics.directory != null) (
          let
            dir = cfg.directories.${cfg.metrics.directory};
          in
          {
            enable = true;
            inherit (dir) repository;
            passwordFile = secretPath dir.passwordSecret;
            rcloneConfigFile = rcloneConfig;
          }
        );
      }

      (lib.mkIf cfg.persist.enable (
        let
          snapshotted = cfg.persist.zfsDataset != null;
          snapshot = "${cfg.persist.zfsDataset}@restic";
          root = if snapshotted then "/run/restic-persist" else "/persist";
        in
        {
          rv32ima.machine.backup.directories."persist" = {
            path = root;
            extraConfig = {
              exclude = map (p: "${root}/${p}") cfg.persist.exclude;
              # always a fresh repo the first time a host turns this on
              initialize = true;
            };
          };

          # everything under /persist belongs to a different service user, so let restic read it all without being root
          systemd.services."restic-backups-persist" = {
            serviceConfig.AmbientCapabilities = [ "CAP_DAC_READ_SEARCH" ];
            requires = lib.optional snapshotted "restic-persist-snapshot.service";
            after = lib.optional snapshotted "restic-persist-snapshot.service";
          };

          # restic's backupPrepareCommand runs as the restic user, so snapshotting lives in its own root unit.
          # StopWhenUnneeded tears the snapshot down as soon as the backup finishes
          systemd.services."restic-persist-snapshot" = lib.mkIf snapshotted {
            path = [
              config.boot.zfs.package
              pkgs.util-linux
            ];
            unitConfig.StopWhenUnneeded = true;
            # a deploy mid-backup would otherwise yank the mount out from under restic
            restartIfChanged = false;
            serviceConfig = {
              Type = "oneshot";
              RemainAfterExit = true;
              ExecStart = pkgs.writeShellScript "restic-persist-snapshot" ''
                set -euo pipefail
                # clean up after a run that died before it could stop us
                if mountpoint -q ${root}; then umount ${root}; fi
                zfs destroy ${snapshot} 2>/dev/null || true
                zfs snapshot ${snapshot}
                mkdir -p ${root}
                mount -t zfs ${snapshot} ${root}
              '';
              ExecStop = pkgs.writeShellScript "restic-persist-snapshot-cleanup" ''
                set -euo pipefail
                if mountpoint -q ${root}; then umount ${root}; fi
                zfs destroy ${snapshot}
              '';
            };
          };
        }
      ))
    ]
  );
}
