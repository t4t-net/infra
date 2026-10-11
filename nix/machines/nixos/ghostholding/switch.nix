{ lib, pkgs, ... }: {
  config =
    let
      bonds = [
        {
          ports = [
            "swp3"
            "swp4"
          ];
        }
        {
          ports = [
            "swp5"
            "swp6"
          ];
        }
        {
          ports = [
            "swp7"
            "swp8"
          ];
        }
      ];

      switchPortMacs = builtins.fromJSON (builtins.readFile ./switch_ports.json);

      bondNetdevs = builtins.listToAttrs (
        lib.imap (
          i: bond:
          let
            bondIface = "bond${builtins.toString i}";
          in
          {
            name = bondIface;
            value = {
              netdevConfig = {
                Kind = "bond";
                Name = bondIface;
                MACAddress = switchPortMacs.${builtins.head bond.ports};
              };
              bondConfig = {
                Mode = "802.3ad";
                TransmitHashPolicy = "layer3+4";
                LACPTransmitRate = "fast";
                MinLinks = 1;
              };
            };
          }
        ) bonds
      );

      bondNetworks = builtins.listToAttrs (
        lib.flatten (
          lib.imap (
            bondIndex: bond:
            (map (port: {
              name = "bond${builtins.toString bondIndex}-${port}";
              value = {
                matchConfig.Name = port;
                networkConfig.Bond = "bond${builtins.toString bondIndex}";
              };
            }) bond.ports)
            ++ [
              {
                name = "bond${builtins.toString bondIndex}";
                value = {
                  matchConfig.Name = "bond${builtins.toString bondIndex}";
                  networkConfig.Bridge = "br-switch";
                  linkConfig = {
                    RequiredForOnline = "carrier";
                  };
                  networkConfig.LinkLocalAddressing = "no";
                };
              }
            ]
          ) bonds
        )
      );
    in
    {
      # mlxsw's ipv4_dhcp devlink trap doesn't fire correctly, so we use a TC
      # flower filter with action trap to force DHCP packets to the CPU via ASIC offload.
      #      systemd.services."tc-dhcp-trap" =
      #        let
      #          # br-switch excluded — redirecting to itself would loop
      #          allInterfaces = lib.flatten (map (b: b.ports) bonds) ++ builtins.attrNames bondNetdevs;
      #        in
      #        {
      #          after = [ "network-online.target" ];
      #          wantedBy = [ "multi-user.target" ];
      #          path = [ pkgs.iproute2 ];
      #          serviceConfig = {
      #            Type = "oneshot";
      #            RemainAfterExit = true;
      #          };
      #          # action trap is not offloaded to HW on mlxsw (not_in_hw), so instead we
      #          # use mirred ingress redirect to inject matched packets directly into
      #          # br-switch's RX path. DHCP broadcasts reach the kernel on swp* via the
      #          # ASIC's normal broadcast flooding, so the software filter catches them.
      #          script = lib.concatMapStrings (iface: ''
      #            tc qdisc add dev ${iface} clsact 2>/dev/null || true
      #            tc filter delete dev ${iface} ingress
      #            # tc filter add dev ${iface} ingress protocol ip flower ip_proto udp dst_port 67 action mirred ingress redirect dev br-switch
      #            # tc filter add dev ${iface} ingress protocol ip flower ip_proto udp dst_port 69 action mirred ingress redirect dev br-switch
      #            # tc filter add dev ${iface} ingress protocol ipv6 flower ip_proto udp dst_port 547 action mirred ingress redirect dev br-switch
      #          '') allInterfaces;
      #        };

      systemd.network.netdevs = bondNetdevs // {
        "br-switch".netdevConfig = {
          Kind = "bridge";
          Name = "br-switch";
          # b0 for bridge0, get it?
          MACAddress = "ec:0d:9a:f9:e4:b0";
        };
      };

      systemd.network.networks = bondNetworks // {
        "br-switch" = {
          matchConfig.Name = "br-switch";
          bridgeConfig = { };

          # Without this, IPv6 neighbor discovery fails, meaning that
          # we appear unreachable to the other side. Don't ask me why this
          # is the way it is.
          addresses = [
            {
              Address = "23.190.72.1/24";
            }
            {
              Address = "2620:C2:2000::1/64";
            }
          ];

          routes = [
            {
              Destination = "2620:c2:2000:1::/64";
              Gateway = "2620:c2:2000::10";
            }
          ];

        };
      };

      networking.firewall.trustedInterfaces = [ "br-switch" ];

      services.atftpd = {
        enable = true;
        root = "${pkgs.rv32ima.ipxe-bootstrap}";
      };

      networking.hosts = {
        "199.255.18.181" = [ "ghostholding.sea.t4t.net" ];
        "2606:7940:32:3c::11" = [ "ghostholding.sea.t4t.net" ];
      };

      services.dnsmasq = {
        enable = true;
        settings = {
          domain = "sea.t4t.net";
          interface = [
            "br-switch"
          ];
          expand-hosts = true;
          enable-ra = true;
          dhcp-authoritative = true;
          enable-tftp = false;

          log-dhcp = true;
          strict-order = true;
          server = [
            "1.1.1.1"
            "1.0.0.1"
            "2606:4700:4700::1111"
            "2606:4700:4700::1001"
          ];
          dhcp-range = [
            "23.190.72.2,23.190.72.254,255.255.255.0,24h"
            "2620:c2:2000::10,2620:c2:2000::200,64,24h"
          ];
          dhcp-option = [
            "option:netmask,255.255.255.0"
            "option:router,23.190.72.1"
            "option:dns-server,23.190.72.1"
            "option:domain-search,sea.t4t.net"
            "option:tftp-server,23.190.72.1"
          ];
          dhcp-vendorclass = [
            "set:BIOS,PXEClient:Arch:00000"
            "set:UEFI32,PXEClient:Arch:00006"
            "set:UEFI,PXEClient:Arch:00007"
            "set:UEFI64,PXEClient:Arch:00009"
          ];
          dhcp-userclass = [
            "set:IPXE,iPXE"
          ];
          # The order for this matters in a way that I don't really like.
          dhcp-boot = [
            "bin/undionly.kpxe"
            "tag:UEFI,bin-x86_64-efi/ipxe.efi"
            "tag:UEFI64,bin-x86_64-efi/ipxe.efi"
          ];
          dhcp-host = [
            "38:05:25:37:2b:d0,23.190.72.45" # peer2peer LACP bond
            "38:05:25:37:2b:d0,[2620:C2:2000::10]" # peer2peer LACP bond
            "0c:42:a1:71:61:06,23.190.72.73" # pawpatch LACP bond
            "0c:42:a1:71:61:06,[2620:C2:2000::16d]" # pawpatch LACP bond
            "0c:42:a1:71:6a:16,23.190.72.231" # psychoboost LACP bond
            "0c:42:a1:71:6a:16,[2620:C2:2000::ea]" # psychoboost LACP bond
          ];
        };
      };

      # Expose dnsmasq to the world. This is probably safe.
      networking.firewall.allowedUDPPorts = [ 53 ];
    };
}
