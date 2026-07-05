{
  config,
  lib,
  pkgs,
  ...
}:
let
  nix-ssh-wrapper = pkgs.writeShellScript "nix-ssh-wrapper" ''
    case $SSH_ORIGINAL_COMMAND in
      "nix-daemon --stdio")
        exec ${config.nix.package}/bin/nix-daemon --stdio
        ;;
      "nix-store --serve --write")
        exec ${config.nix.package}/bin/nix-store --serve --write
        ;;
      *)
        echo "Access only allowed for using the nix remote builder" 1>&2
        exit
    esac
  '';
in
{
  options.rv32ima.machine.remote-builder.key = lib.mkOption {
    type = lib.types.singleLineStr;
    default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHYuMJ2VhzIpdQ158PvX2SH+8HRJ3Y4nbYvzNcPuaPI+ builder@localhost";
    description = "ssh public key for the remote build user";
  };

  config = {
    users.users.nix.openssh.authorizedKeys.keys = [
      # use nix-store for hydra which doesn't support ssh-ng
      ''restrict,command="${nix-ssh-wrapper}" ${config.rv32ima.machine.remote-builder.key}''
    ];
    users.users.nix.openssh.authorizedPrincipals = [
      "ellie"
      ''command="${nix-ssh-wrapper}",restrict repo:t4t-net/infra:ref:refs/heads/main''
    ];

    nix.settings.trusted-users = [ "nix" ];

    users.users.nix = {
      isNormalUser = true;
      group = "nix";
      home = "/var/lib/nix";
      createHome = true;
    };

    users.groups.nix = { };
  };
}
