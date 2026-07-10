{ pkgs, ... }:
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/nzbget;
        mode = "0700";
        owner = "nzbget";
        group = "nzbget";
      }
    ];

    services.nzbget.enable = true;
    rv32ima.machine.tailscale.services.pawpatch-nzbget = {
      targetUnit = "nzbget.service";
      port = 6789;
    };
  };
}
