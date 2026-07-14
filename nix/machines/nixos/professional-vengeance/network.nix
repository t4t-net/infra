{ lib, ... }:
{
  networking.useDHCP = lib.mkDefault false;
  networking.useNetworkd = true;
  networking.firewall.checkReversePath = "loose";

  systemd.network.networks."bond0" = {
    matchConfig.PermanentMACAddress = "BC:24:11:65:29:37";

    networkConfig = {
      DHCP = true;
      IPv6AcceptRA = true;
    };

    dhcpV6Config.WithoutRA = "solicit";
  };
}
