{ lib, ... }:
{
  networking.useDHCP = lib.mkDefault false;
  networking.useNetworkd = true;
  networking.firewall.checkReversePath = "loose";

  systemd.network.networks."01-ethernet" = {
    matchConfig.PermanentMACAddress = "64:4b:f0:38:a0:cc";

    networkConfig = {
      DHCP = true;
      IPv6AcceptRA = true;
    };

    dhcpV6Config.WithoutRA = "solicit";
  };
}
