{
  inputs,
  config,
  pkgs,
  self,
  ...
}:
let
  pkgsUnstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
  };
in
{
  imports = [
    (self.lib.nixosModule "nixos/digitalocean-image")
    (self.lib.nixosModule "nixos/home-manager")
    (self.lib.nixosModule "nixos/update-dotfiles")
    (self.lib.nixosModule "nixos/machine-certificate")
    (self.lib.nixosModule "nixos/impermanence")
    (self.lib.nixosModule "nixos/deploy")
    (self.lib.nixosModule "nixos/backup")
    (self.lib.nixosModule "nixos/services/tailscale")
    (self.lib.nixosModule "nixos/services/step-ca")

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")
  ];

  config = {
    boot.initrd.availableKernelModules = [
      "ahci"
      "xhci_pci"
      "megaraid_sas"
      "usbhid"
      "usb_storage"
      "sd_mod"
      "sr_mod"
    ];
    boot.initrd.kernelModules = [ ];
    boot.kernelModules = [ ];
    boot.extraModulePackages = [ ];

    # head -c4 /dev/urandom | od -A none -t x4
    networking.hostId = "1af5b3bb";

    rv32ima.machine.tailscale.enable = true;

    # no luks on the droplet, so it can reboot for kernels on its own
    rv32ima.machine.hydraDeploy = {
      enable = true;
      allowReboot = true;
      rebootWindow = {
        lower = "05:00";
        upper = "06:00";
      };
    };

    # no /persist (or zfs) on a droplet, so name th state we care about instead of persist.enable.
    # reuses th one password that's already in restic.yaml
    rv32ima.machine.backup = {
      enable = true;
      secretsFile = ./secrets/restic.yaml;
      directories."postgresql" = {
        path = config.services.postgresqlBackup.location;
        passwordSecret = "services/restic/persist/password";
        extraConfig.initialize = true;
      };
    };

    # a live postgres data dir isn't safe to copy without a snapshot, so back up a dump instead.
    # no timer of its own, th restic unit below pulls it in right before each backup
    services.postgresqlBackup = {
      enable = true;
      databases = [ "step-ca" ];
      startAt = [ ];
      # restic dedups + compresses on its own, and gzip would defeat th dedup
      compression = "none";
    };

    systemd.services."restic-backups-postgresql" = {
      requires = [ "postgresqlBackup-step-ca.service" ];
      after = [ "postgresqlBackup-step-ca.service" ];
      # th dump is postgres-only, let restic read it without being root
      serviceConfig.AmbientCapabilities = [ "CAP_DAC_READ_SEARCH" ];
    };

    services.prometheus.exporters.node.enable = true;

    services.openssh.enable = true;
    services.openssh.openFirewall = true;

    programs.fish.enable = true;
    programs.fish.useBabelfish = true;

    networking.domain = "sfo.t4t.net";
    system.primaryUser = "ellie";
  };
}
