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
        hostName = "nixos-builders-x86-64-linux-1.tail1256ba.ts.net";
        sshUser = "nix";
        protocol = "ssh-ng";
        maxJobs = 8;
        system = "x86_64-linux";
        publicHostKey = "c3NoLWVkMjU1MTkgQUFBQUMzTnphQzFsWkRJMU5URTVBQUFBSUJYcUUrVXVFdVZFTjZLUWo5R2Vlb2hvVXdMV2FXRndwSkF2UEM0dzlGbFE=";
      }
      {
        hostName = "nixos-builders-x86-64-linux-2.tail1256ba.ts.net";
        sshUser = "nix";
        protocol = "ssh-ng";
        maxJobs = 8;
        system = "x86_64-linux";
        publicHostKey = "c3NoLWVkMjU1MTkgQUFBQUMzTnphQzFsWkRJMU5URTVBQUFBSUhLWWczUUtXK1oxb2YrQzBFQThDdzhNeXl6djE4Q0hCU2dVa0pFZlYyKzc=";
      }
      {
        hostName = "nixos-builders-x86-64-linux-3.tail1256ba.ts.net";
        sshUser = "nix";
        protocol = "ssh-ng";
        maxJobs = 8;
        system = "x86_64-linux";
        publicHostKey = "c3NoLWVkMjU1MTkgQUFBQUMzTnphQzFsWkRJMU5URTVBQUFBSUoxcFcwUUhMVlZQVzBjMXZpVWJCY1ZQVldVT0pJay9CcThnQk5kTlE0UmI=";
      }
      {
        hostName = "nixos-builders-x86-64-linux-4.tail1256ba.ts.net";
        sshUser = "nix";
        protocol = "ssh-ng";
        maxJobs = 8;
        system = "x86_64-linux";
        publicHostKey = "c3NoLWVkMjU1MTkgQUFBQUMzTnphQzFsWkRJMU5URTVBQUFBSUJudzZQR1dwdlRaVkpGRFBXOU5PZEc5UUMxd1NVUngxWlRGMmVZY1RyMFo=";
      }
      {
        hostName = "nixos-builders-x86-64-linux-5.tail1256ba.ts.net";
        sshUser = "nix";
        protocol = "ssh-ng";
        maxJobs = 8;
        system = "x86_64-linux";
        publicHostKey = "c3NoLWVkMjU1MTkgQUFBQUMzTnphQzFsWkRJMU5URTVBQUFBSUhuVzZ0Y28vanIvK2VGaDlBdFpEMFAzbklueHBrOW9rY3ZuYXVndEFjVVo=";
      }
    ];

    system.stateVersion = 6;
    system.primaryUser = "eford";
    nixpkgs.hostPlatform = "aarch64-darwin";
  };
}
