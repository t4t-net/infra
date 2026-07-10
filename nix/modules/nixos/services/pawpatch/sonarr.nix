{ ... }:
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/sonarr/.config/NzbDrone;
        mode = "0770";
        owner = "sonarr";
        group = "sonarr";
      }
    ];

    services.sonarr.enable = true;

    rv32ima.machine.tailscale.services.pawpatch-sonarr = {
      targetUnit = "sonarr.service";
      port = 8989;
    };
  };
}
