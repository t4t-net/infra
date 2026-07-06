{
  inputs,
  lib,
  self,
  ...
}:
{
  imports = [
    ./network.nix
    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "nixos/netboot")

    inputs.nixos-hardware.nixosModules.framework-amd-ai-300-series
  ];

  config = {
    environment.systemPackages = [
      inputs.disko.packages.x86_64-linux.default
    ];

    # boot.loader.efi.canTouchEfiVariables = true;
    # boot.loader.grub.efiSupport = true;
    # boot.loader.grub.efiInstallAsRemovable = true;
    # boot.loader.grub.device = "nodev";

    # isoImage.squashfsCompression = "gzip -Xcompression-level 1";
    systemd.services.sshd.wantedBy = lib.mkForce [ "multi-user.target" ];
    users.users.root.openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPUAs4RQBUriBrp7rv2cepCve5eIo6uqFfgs7oPqV9Q" # 1Password -> 'Primary SSH key'
    ];

    networking.firewall.allowedTCPPorts = [
      22
    ];

    nixpkgs.hostPlatform = "x86_64-linux";
    system.stateVersion = "26.05";
    networking.domain = "home.t4t.net";
  };
}
