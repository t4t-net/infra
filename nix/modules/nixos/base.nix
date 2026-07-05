# Set of sanity-keeping configurations.
# All machines should import this module.

{
  lib,
  self,
  pkgs,
  vars',
  inputs,
  ...
}:

{
  imports = [
    inputs.disko.nixosModules.disko
    inputs.sops-nix.nixosModules.sops
    (self.lib.nixosModule "shared/nix-config")
    (self.lib.nixosModule "shared/nixpkgs")
  ];

  options = {
    # Define this for parity with nix-darwin, which has this defined.
    system.primaryUser = lib.mkOption {
      type = lib.types.str;
    };
  };

  config = {
    systemd.settings.Manager = {
      # Don't wait too long for services to stop:
      DefaultTimeoutStopSec = "15s";
      # Prevent the system from hanging:
      RuntimeWatchdogSec = "5m";
      ShutdownWatchdogSec = "15m";
    };

    services.journald.extraConfig = ''
      SystemMaxUse=2G
      MaxRetentionSec=3month
    '';

    services.openssh.extraConfig = ''
      TrustedUserCAKeys ${../../../certificates/ssh-user-ca.pub}
    '';

    # Probably needed in some systems:
    hardware.enableRedistributableFirmware = true;

    # All overlays.
    nixpkgs.overlays = [
      (final: prev: {
        disko = inputs.disko.packages.${pkgs.system}.default;
      })
    ]
    ++ builtins.attrValues self.overlays;

    # Useful tools.
    environment.systemPackages = with pkgs; [
      htop
      jq
      vim
      wget
      disko
      sbctl
      # persistent terminal sessions for ssh
      tmux
      # useful for getting metal host information
      dmidecode
    ];

    environment.sessionVariables = {
      FLAKE = self;
    };

    # Where we are roughly:
    time.timeZone = "America/Los_Angeles";

    # Since impermanence currently screws up machine-id, manually override it to
    # whatever is in vars:
    environment.etc =
      (lib.optionalAttrs (vars' ? machineID) { machine-id.text = vars'.machineID; })
      // {
        "ca.t4t.net.crt".text = builtins.readFile ../../../certificates/root-ca.crt;
      };
    boot.kernelParams = lib.optional (vars' ? machineID) "systemd.machine_id=${vars'.machineID}";

    security.pki.certificates = [
      ''
        ca.t4t.net
        =========
        ${builtins.readFile ../../../certificates/root-ca.crt}
      ''
    ];

    # Enable node-exporter by default for Prometheus monitoring.
    services.prometheus.exporters.node = {
      enable = true;
    };

    users.groups.trusted = { };
    # users in trusted group are trusted by the nix-daemon
    nix.settings.trusted-users = [ "@trusted" ];

    nix.settings.substituters = [
      "https://cache.t4t.net"
    ];

    nix.settings.trusted-public-keys = [
      "cache.t4t.net-1:7NimrD/skv9tL7c3UjgwMxpup/RNcvzd7yrH0QNnlF0="
    ];

    # Manage users atomically
    users.mutableUsers = false;

    # The notion of "online" is a broken concept
    # https://github.com/systemd/systemd/blob/e1b45a756f71deac8c1aa9a008bd0dab47f64777/NEWS#L13
    #     services.networkma
    networking.networkmanager.enable = lib.mkForce false;
    systemd.services.NetworkManager-wait-online.enable = false;
    systemd.network.wait-online.enable = false;

    nixpkgs.hostPlatform = vars'.system;
    system.stateVersion = vars'.stateVersion;
  };
}
