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
in
{
  options = {
    rv32ima.machine.backup.enable = lib.mkEnableOption "restic backups";

    rv32ima.machine.backup.secretsFile = lib.mkOption {
      type = lib.types.path;
      description = "sops file holding the password and rclone config for each backed up directory";
    };

    rv32ima.machine.backup.repositoryBase = lib.mkOption {
      type = lib.types.str;
      default = "rclone:secret:restic/${config.networking.hostName}";
      description = "prefix for every repository on this host; each directory gets <repositoryBase>/<name>";
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
              rcloneConfigSecret = lib.mkOption {
                type = lib.types.str;
                default = "services/restic/${name}/rcloneConfig";
              };
              extraConfig = lib.mkOption {
                type = lib.types.attrs;
                default = { };
                description = "extra options merged into services.restic.backups.<name> (timerConfig, pruneOpts, exclude, ...)";
              };
            };
          }
        )
      );
      default = { };
    };
  };

  config = lib.mkIf cfg.enable {
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

    sops.secrets = lib.concatMapAttrs (_: dir: {
      ${dir.passwordSecret} = secretOpts;
      ${dir.rcloneConfigSecret} = secretOpts;
    }) cfg.directories;

    services.restic.backups = lib.mapAttrs (
      _: dir:
      {
        inherit (dir) repository;
        user = config.users.users."restic".name;
        paths = [ dir.path ];
        passwordFile = secretPath dir.passwordSecret;
        rcloneConfigFile = secretPath dir.rcloneConfigSecret;
      }
      // dir.extraConfig
    ) cfg.directories;

    # rclone-<name>, alongside the restic-<name> wrappers nixpkgs already generates.
    # the secrets are only readable by restic, so run these as `sudo -u restic rclone-<name> ...`
    environment.systemPackages = lib.mapAttrsToList (
      name: dir:
      pkgs.writeShellScriptBin "rclone-${name}" ''
        export RCLONE_CONFIG=${secretPath dir.rcloneConfigSecret}
        exec ${lib.getExe pkgs.rclone} "$@"
      ''
    ) cfg.directories;

    services.prometheus.exporters.restic = lib.mkIf (cfg.metrics.directory != null) (
      let
        dir = cfg.directories.${cfg.metrics.directory};
      in
      {
        enable = true;
        inherit (dir) repository;
        passwordFile = secretPath dir.passwordSecret;
        rcloneConfigFile = secretPath dir.rcloneConfigSecret;
      }
    );
  };
}
