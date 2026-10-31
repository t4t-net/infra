{ pkgs, ... }:
{
  config = {
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
    services.plex.package = pkgs.unstable.plex;
  };
}
