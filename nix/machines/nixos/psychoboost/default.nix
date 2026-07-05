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
    (self.lib.nixosModule "nixos/services/hydra")

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")

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
    boot.kernelModules = [ "kvm-amd" ];
    boot.extraModulePackages = [ ];

    # head -c4 /dev/urandom | od -A none -t x4
    networking.hostId = "6c0d5ca5";

    rv32ima.machine.tailscale.enable = true;

    services.prometheus.exporters.node.enable = true;

    services.openssh.enable = true;
    services.openssh.openFirewall = false;

    programs.fish.enable = true;
    programs.fish.useBabelfish = true;

    networking.useNetworkd = true;
    networking.firewall.allowedTCPPorts = [ ];
    networking.firewall.logRefusedConnections = false;

    nix.buildMachines = [
      (self.lib.machineAsBuilder "unmusique")
      (self.lib.machineAsBuilder "peer2peer")
    ];

    sops.secrets."services/nix/github-access-token" = {
      sopsFile = ./secrets/nix.yaml;
      # We want this world-readable, since it only provides read-only access to public
      # repositories and nothing more.
      mode = "0444";
    };

    nix.extraOptions = ''
      !include ${config.sops.secrets."services/nix/github-access-token".path}
    '';

    services.zfs.autoScrub.enable = true;
    services.zfs.autoScrub.interval = "weekly";

    networking.domain = "sea.t4t.net";
    system.primaryUser = "ellie";
  };
}
