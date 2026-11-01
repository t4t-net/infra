{
  config,
  pkgs,
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
    (self.lib.nixosModule "nixos/services/tailscale")
    (self.lib.nixosModule "nixos/services/llama-cpp")
    # No machine-certificate since this lives at home and is behind
    # NAT.

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")

    ./network.nix
    ./disk-config.nix

    inputs.nixos-hardware.nixosModules.framework-desktop-amd-ai-max-300-series
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
      # vm definitions, nvram, networks nd th default image pool all live here
      {
        path = /var/lib/libvirt;
        mode = "0755";
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
      # 120GiB of gtt. in-tree amdgpu, so ttm.* and not th dkms amdttm.* names!!
      "ttm.pages_limit=31457280"
      "ttm.page_pool_size=31457280"
      # 8GiB. arc defaults 2 nearly all of ram nd fights gtt while big models load
      "zfs.zfs_arc_max=8589934592"
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

    hardware.graphics = {
      enable = true;
      enable32Bit = true;
    };

    services.displayManager.gdm.enable = true;
    services.desktopManager.gnome.enable = true;

    programs.virt-manager.enable = true;
    virtualisation.libvirtd.enable = true;
    # th stock unit seals this key w /var/lib/systemd/credential.secret, which th root rollback
    # wipes, so a persisted key goes undecryptable on th next boot. tpm-only has no such file!!
    # if pcr 7 ever changes libvirtd wont start: delete th key nd restart it 2 make a new one
    systemd.services.virt-secret-init-encryption.serviceConfig.ExecStart = [
      ""
      (pkgs.writeShellScript "virt-secret-init-encryption" ''
        set -euo pipefail
        umask 0077
        ${pkgs.coreutils}/bin/dd if=/dev/random status=none bs=32 count=1 |
          ${config.systemd.package}/bin/systemd-creds encrypt \
            --with-key=tpm2 --tpm2-pcrs=7 --name=secrets-encryption-key - \
            /var/lib/libvirt/secrets/secrets-encryption-key
      '')
    ];

    rv32ima.machine.tailscale.enable = true;

    # luks unlocks itself from th tpm2, so it can reboot for kernels on its own
    rv32ima.machine.hydraDeploy = {
      enable = true;
      allowReboot = true;
    };

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
