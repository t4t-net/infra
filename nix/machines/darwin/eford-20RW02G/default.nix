{
  self,
  config,
  lib,
  ...
}:
{
  imports = [
    (self.lib.nixosModule "darwin/workstation")
    (self.lib.nixosModule "darwin/nix-sshd-proxy")
    (self.lib.nixosModule "darwin/linux-builder")
    (self.lib.nixosModule "users/eford")
  ];
  config = {
    rv32ima.machine.workstation.enable = true;

    services.tailscale.enable = lib.mkForce false;

    nix.settings.trusted-users = [
      "${config.system.primaryUser}"
    ];

    nix.settings.trusted-public-keys = [
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "cache.tvscids.net-1:FZCEhH4KgWQ/1VWZehUCiKaVvfPPEzjjl11NJ4kbVbg="
    ];

    nix.settings.trusted-substituters = [
      "https://nix-community.cachix.org"
      "https://nix-cache.tail1256ba.ts.net"
    ];

    nix.settings.max-jobs = 10;
    nix.distributedBuilds = true;
    nix.buildMachines = [
      {
        hostName = "nix-build-x86-64-01.tail1256ba.ts.net";
        sshUser = "nix";
        sshKey = "/Users/${config.system.primaryUser}/code/ds/.keys/builder_ed25519";
        protocol = "ssh-ng";
        maxJobs = 16;
        system = "x86_64-linux";
        publicHostKey = "c3NoLWVkMjU1MTkgQUFBQUMzTnphQzFsWkRJMU5URTVBQUFBSUVva0NJekFERWFOaXR2cENDNjhZNk9oOWhMUVJiVFRFSnV0c3k5ZlNNVk0K";
      }
    ];

    system.stateVersion = 6;
    system.primaryUser = "eford";
    nixpkgs.hostPlatform = "aarch64-darwin";
  };
}
