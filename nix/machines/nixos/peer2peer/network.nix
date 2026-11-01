{ config, lib, ... }:
{
  networking.useDHCP = lib.mkDefault false;
  networking.useNetworkd = true;
  networking.firewall.checkReversePath = "loose";

  systemd.network.networks."01-vpro-oob-ethernet" = {
    enable = true;
    matchConfig.PermanentMACAddress = "38:05:25:38:07:AE";
    DHCP = "yes";
  };

  systemd.network.netdevs."bond0".netdevConfig = {
    Kind = "bond";
    Name = "bond0";
    MACAddress = "38:05:25:37:2b:d0";
  };

  systemd.network.netdevs."bond0".bondConfig = {
    Mode = "802.3ad";
    TransmitHashPolicy = "layer3+4";
    LACPTransmitRate = "fast";
  };

  systemd.network.networks."bond0-eno1np0" = {
    matchConfig.Name = "eno1np0";
    networkConfig.Bond = "bond0";
  };

  systemd.network.networks."bond0-eno2np1" = {
    matchConfig.Name = "eno2np1";
    networkConfig.Bond = "bond0";
  };

  systemd.network.networks."bond0" = {
    matchConfig.Name = "bond0";

    networkConfig = {
      DHCP = true;
      IPv6AcceptRA = true;
    };

    dhcpV6Config.WithoutRA = "solicit";
  };

  systemd.network.netdevs."home-wg" = {
    netdevConfig = {
      Kind = "wireguard";
      Name = "home-wg";
    };
    wireguardConfig = {
      ListenPort = 51820;
      RouteTable = "main";
      PrivateKeyFile = "/persist/etc/wireguard/secret.key";
    };
    wireguardPeers = [
      {
        AllowedIPs = [
          "10.100.0.2/32"
        ];
        PublicKey = "XbQNGT/bWtBJ/4i3UupI7tsMHUevYcbkHJwTv7QUVDY=";
      }
    ];
  };

  networking.firewall.allowedUDPPorts = [
    51820
    51821
  ];

  systemd.network.networks."home-wg" = {
    matchConfig.Name = "home-wg";

    networkConfig.Tunnel = "home-sit";

    address = [
      "10.100.0.1/32"
    ];
  };

  boot.kernelModules = [
    "sit"
  ];

  systemd.network.netdevs."home-sit" = {
    netdevConfig = {
      Kind = "sit";
      Name = "home-sit";
      MTUBytes = 1400;
    };
    tunnelConfig = {
      Local = "10.100.0.1";
      Remote = "10.100.0.2";
      TTL = 255;
    };
  };

  systemd.network.networks."home-sit" = {
    matchConfig.Name = "home-sit";

    linkConfig = {
      MTUBytes = 1400;
    };

    routes = [
      {
        Destination = "2620:c2:2000:1::/64";
      }
    ];
  };

  # iris's way onto AS395388: ghostholding routes her addresses here nd they go down this tunnel.
  # keep this box's private key out of her reach, all she holds is her own end
  sops.secrets."wireguard/iris-private-key" = {
    sopsFile = ./secrets/wireguard.yaml;
    key = "private-key";
    owner = "systemd-network";
    restartUnits = [ "systemd-networkd.service" ];
  };

  systemd.network.netdevs."wg-iris" = {
    netdevConfig = {
      Kind = "wireguard";
      Name = "wg-iris";
    };
    wireguardConfig = {
      ListenPort = 51821;
      RouteTable = "main";
      PrivateKeyFile = config.sops.secrets."wireguard/iris-private-key".path;
    };
    wireguardPeers = [
      {
        AllowedIPs = [
          "23.190.72.254/32"
          "2620:c2:2000:2::/64"
        ];
        PublicKey = "sbyNqkiGvVEsShtd/gKOmOEddqNX5jCFtAZ1hUjuFUA=";
      }
    ];
  };

  systemd.network.networks."wg-iris".matchConfig.Name = "wg-iris";

  # she reads untrusted input, so what comes out of this tunnel only gets th internet: not th tailnet,
  # not podman, not th /24 or anything private behind ghostholding. mangle cuz tailscaled re-inserts
  # ts-forward at th top of filter FORWARD nd that ends in `-o tailscale0 -j ACCEPT`.
  # port 25 stays shut so a prompt injection cant burn th reputation of th whole /24
  networking.firewall.extraCommands = ''
    ip46tables -t mangle -D FORWARD -i wg-iris -j iris-egress 2>/dev/null || true
    ip46tables -t mangle -F iris-egress 2>/dev/null || true
    ip46tables -t mangle -X iris-egress 2>/dev/null || true
    ip46tables -t mangle -N iris-egress
    ip46tables -t mangle -A iris-egress ! -o bond0 -j DROP
    ip46tables -t mangle -A iris-egress -p tcp --dport 25 -j DROP
    iptables -t mangle -A iris-egress -d 10.0.0.0/8,100.64.0.0/10,169.254.0.0/16,172.16.0.0/12,192.168.0.0/16,23.190.72.0/24 -j DROP
    ip6tables -t mangle -A iris-egress -d fc00::/7,2620:c2:2000::/48 -j DROP
    ip46tables -t mangle -A FORWARD -i wg-iris -j iris-egress
  '';
  networking.firewall.extraStopCommands = ''
    ip46tables -t mangle -D FORWARD -i wg-iris -j iris-egress 2>/dev/null || true
    ip46tables -t mangle -F iris-egress 2>/dev/null || true
    ip46tables -t mangle -X iris-egress 2>/dev/null || true
  '';

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = "1";
    "net.ipv6.conf.all.forwarding" = "1";
    "net.ipv6.conf.default.forwarding" = "1";
  };

  networking.firewall.trustedInterfaces = [
    "home-wg"
    "home-sit"
  ];
}
