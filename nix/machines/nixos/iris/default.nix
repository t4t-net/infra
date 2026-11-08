{
  self,
  ...
}:
# iris th foxgirl!! a hermes agent reachable from discord, so everything she reads is untrusted.
# she gets as little of th fleet as possible: no users/root (that decrypts th shared root password
# hash), no users/ellie, no machine-certificate, no home-manager or dotfiles
{
  imports = [
    (self.lib.nixosModule "nixos/digitalocean-image")
    (self.lib.nixosModule "nixos/services/tailscale")
    (self.lib.nixosModule "nixos/services/hermes-agent")
    (self.lib.nixosModule "nixos/services/anthropic-proxy")
    (self.lib.nixosModule "nixos/services/hevy-mcp")
    (self.lib.nixosModule "nixos/services/ynab-mcp")

    ./network.nix
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
    networking.hostId = "9bca2bf7";

    rv32ima.machine.tailscale.enable = true;

    # no luks on th droplet, so it can reboot for kernels on its own
    rv32ima.machine.hydraDeploy = {
      enable = true;
      allowReboot = true;
      rebootWindow = {
        lower = "05:00";
        upper = "06:00";
      };
      # her own webhook, cuz th shared one is th fleet's nd she shouldnt hold any fleet secrets
      discord.sopsFile = ./secrets/hydra-deploy.yaml;
    };

    users.users.root.openssh = {
      authorizedPrincipals = [
        "ellie"
        "me@ellie.fm"
      ];
      authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPUAs4RQBUriBrp7rv2cepCve5eIo6uqFfgs7oPqV9Q" # 1Password -> 'Primary SSH key'
      ];
    };

    services.prometheus.exporters.node.enable = true;

    # tailscale only. she dials out, nothing on th internet needs 2 reach her
    services.openssh.enable = true;
    services.openssh.openFirewall = false;

    networking.domain = "sfo.t4t.net";
  };
}
