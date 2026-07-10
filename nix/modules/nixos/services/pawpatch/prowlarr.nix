{ ... }:
{
  config = {
    services.prowlarr.enable = true;
    rv32ima.machine.tailscale.services.pawpatch-prowlarr = {
      targetUnit = "prowlarr.service";
      port = 9696;
    };
  };
}
