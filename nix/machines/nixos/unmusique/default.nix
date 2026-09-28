{
  config,
  inputs,
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
    (self.lib.nixosModule "nixos/impermanence")
    (self.lib.nixosModule "nixos/home-manager")
    (self.lib.nixosModule "nixos/update-dotfiles")
    (self.lib.nixosModule "nixos/zfs-mirror")
    (self.lib.nixosModule "nixos/remote-builder")
    (self.lib.nixosModule "nixos/deploy")
    (self.lib.nixosModule "nixos/machine-certificate")
    (self.lib.nixosModule "nixos/backup")
    (self.lib.nixosModule "nixos/services/tailscale")
    (self.lib.nixosModule "nixos/services/grafana")
    (self.lib.nixosModule "nixos/services/tailscalesd")
    (self.lib.nixosModule "nixos/services/tsidp")
    (self.lib.nixosModule "nixos/services/victoria-metrics")
    (self.lib.nixosModule "nixos/services/openbao")

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")

    ./network.nix
  ];

  config = {
    rv32ima.machine.enableZfsMirror = true;
    rv32ima.machine.zfsMirrorDisks = [
      "/dev/disk/by-id/ata-MK000480GZXRA_S6M8NE0RC00250"
      "/dev/disk/by-id/ata-MK000480GZXRA_S6M8NE0T100628"
    ];
    rv32ima.machine.impermanence.enable = true;
    rv32ima.machine.impermanence.extraPersistDirectories = [ ];

    services.getty.autologinUser = "root";

    boot.initrd.availableKernelModules = [
      "ahci"
      "xhci_pci"
      "megaraid_sas"
      "usbhid"
      "usb_storage"
      "sd_mod"
      "sr_mod"
      "hpsa"
    ];
    boot.initrd.kernelModules = [ ];
    boot.kernelModules = [ "kvm-intel" ];
    boot.extraModulePackages = [ ];

    networking.hostId = "b89ce780";

    rv32ima.machine.tailscale.enable = true;

    rv32ima.machine.backup = {
      enable = true;
      secretsFile = ./secrets/restic.yaml;
      persist.enable = true;
    };

    services.openssh.enable = true;
    services.openssh.openFirewall = false;

    programs.fish.enable = true;
    programs.fish.useBabelfish = true;

    networking.useNetworkd = true;
    networking.firewall.allowedTCPPorts = [ ];

    system.primaryUser = "ellie";
    networking.domain = "sea.t4t.net";
  };
}
