{
  config,
  inputs,
  lib,
  self,
  vars,
  ...
}:
let
  pkgsUnstable = import inputs.nixpkgs-unstable {
    system = config.rv32ima.machine.platform;
  };
in
{
  imports = [
    (self.lib.nixosModule "darwin/workstation")
    (self.lib.nixosModule "darwin/linux-builder")
    (self.lib.nixosModule "users/ellie")
  ];

  config = {
    rv32ima.machine.workstation.enable = true;

    # Tailscale Split DNS doesn't work with the OSS-built
    # client, like what comes from Nix. Alas, we have to use the "real" version that
    # uses a kernel extension.
    services.tailscale.enable = lib.mkForce false;
    services.tailscale.package = pkgsUnstable.tailscale;
    homebrew = {
      casks = [
        "tailscale-app"
      ];
    };

    nix.linux-builder = {
      enable = true;
      ephemeral = true;
      maxJobs = 10;
    };

    nix.distributedBuilds = true;
    nix.settings.max-jobs = 10;
    nix.buildMachines = [
      (self.lib.machineAsBuilder "peer2peer")
      (self.lib.machineAsBuilder "psychoboost")
    ];

    system.stateVersion = 6;
    system.primaryUser = "ellie";
    nixpkgs.hostPlatform = "aarch64-darwin";
    networking.domain = "net.ellie.fm";
  };
}
