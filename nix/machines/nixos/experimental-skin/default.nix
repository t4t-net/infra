{
  self,
  inputs,
  ...
}:
{
  imports = [
    (self.lib.nixosModule "nixos/impermanence")
    (self.lib.nixosModule "nixos/home-manager")
    (self.lib.nixosModule "nixos/update-dotfiles")
    (self.lib.nixosModule "nixos/remote-builder")
    (self.lib.nixosModule "nixos/deploy")
    (self.lib.nixosModule "nixos/services/tailscale")
    # No machine-certificate since this lives at home and is behind
    # NAT.

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")

    ./network.nix
    ./disk-config.nix

    inputs.nixos-hardware.nixosModules.framework-amd-ai-300-series
  ];

  config = {
    # Automatically authorize any new Thunderbolt devices plugged into our system.
    # This is totally not secure.
    services.udev.extraRules = ''
      ACTION=="add", SUBSYSTEM=="thunderbolt", ATTR{authorized}=="0", ATTR{authorized}="1"
    '';

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
    boot.loader.limine.extraEntries = ''
      /Windows 11
        protocol: efi
        path: guid(6835-BA6A):/EFI/Microsoft/Boot/bootmgfw.efi
        comment: Boot into Windows 11
    '';

    boot.kernelParams = [
      "amdttm.pages_limit=27648000"
      "amdttm.page_pool_size=27648000"
    ];

    boot.initrd.availableKernelModules = [
      "ahci"
      "xhci_pci"
      "megaraid_sas"
      "usbhid"
      "usb_storage"
      "sd_mod"
      "sr_mod"
      "nvme"
    ];
    boot.initrd.kernelModules = [ ];
    boot.kernelModules = [ "kvm-amd" ];
    boot.extraModulePackages = [ ];

    # head -c4 /dev/urandom | od -A none -t x4
    networking.hostId = "5a05f268";

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

    hardware.enableRedistributableFirmware = true;
    hardware.amdgpu.initrd.enable = true;

    networking.domain = "home.t4t.net";
    system.primaryUser = "ellie";
  };
}
