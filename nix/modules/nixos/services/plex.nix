{ inputs, pkgs, ... }:
{
  config =
    let
      pkgsUnstable = import inputs.nixpkgs-unstable {
        system = pkgs.stdenv.hostPlatform.system;
      };
    in
    {
      rv32ima.machine.impermanence.extraPersistDirectories = [
        {
          path = /var/lib/plex;
          mode = "0770";
          owner = "plex";
          group = "plex";
        }
      ];
      services.plex.enable = true;
      services.plex.openFirewall = true;
      services.plex.dataDir = "/var/lib/plex";
      services.plex.package = pkgsUnstable.plex;
    };
}
