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
    (self.lib.nixosModule "nixos/impermanence")
    (self.lib.nixosModule "nixos/home-manager")
    (self.lib.nixosModule "nixos/update-dotfiles")
    (self.lib.nixosModule "nixos/remote-builder")
    (self.lib.nixosModule "nixos/deploy")
    (self.lib.nixosModule "nixos/machine-certificate")
    (self.lib.nixosModule "nixos/services/tailscale")
    (self.lib.nixosModule "nixos/services/plex")
    (self.lib.nixosModule "nixos/services/pawpatch/copyparty")
    (self.lib.nixosModule "nixos/services/pawpatch/soulseek")
    (self.lib.nixosModule "nixos/services/pawpatch/vintagestory")
    (self.lib.nixosModule "nixos/services/pawpatch/vintagestory-eval")
    (self.lib.nixosModule "nixos/services/pawpatch/prowlarr")
    (self.lib.nixosModule "nixos/services/pawpatch/radarr")
    (self.lib.nixosModule "nixos/services/pawpatch/lidarr")
    (self.lib.nixosModule "nixos/services/pawpatch/sonarr")
    (self.lib.nixosModule "nixos/services/pawpatch/overseerr")
    (self.lib.nixosModule "nixos/services/pawpatch/nzbget")
    (self.lib.nixosModule "nixos/services/pawpatch/unpackerr")

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")
    (self.lib.nixosModule "users/chloe")

    ./network.nix
    ./disk-config.nix
  ];

  config = {

    rv32ima.machine.impermanence.enable = true;
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/sbctl;
        mode = "0644";
        owner = "root";
        group = "root";
      }
    ];

    boot.loader.limine.enable = true;
    boot.loader.limine.secureBoot.enable = true;
    boot.loader.limine.efiInstallAsRemovable = true;

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
    boot.kernelModules = [ "kvm-intel" ];
    boot.extraModulePackages = [ ];

    # head -c4 /dev/urandom | od -A none -t x4
    networking.hostId = "93db2077";

    rv32ima.machine.tailscale.enable = true;

    services.prometheus.exporters.node.enable = true;

    services.openssh.enable = true;
    services.openssh.openFirewall = false;

    programs.fish.enable = true;
    programs.fish.useBabelfish = true;

    networking.useNetworkd = true;
    networking.firewall.allowedTCPPorts = [ ];
    networking.firewall.logRefusedConnections = false;

    services.zfs.autoScrub.enable = true;
    services.zfs.autoScrub.interval = "weekly";

    networking.domain = "sea.t4t.net";
    system.primaryUser = "ellie";
  };
}
