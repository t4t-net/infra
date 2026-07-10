{ ... }:
{
  config = {
    services.prowlarr.enable = true;
    rv32ima.machine.tailscale.services.pawpatch-prowlarr = {
      port = 9696;
    };
  };
}
