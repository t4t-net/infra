{ ... }:
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/lidarr/.config/Lidarr;
        mode = "0770";
        owner = "lidarr";
        group = "lidarr";
      }
    ];

    services.lidarr.enable = true;
    rv32ima.machine.tailscale.services.pawpatch-lidarr = {
      targetUnit = "lidarr.service";
      port = 8686;
    };
  };
}
