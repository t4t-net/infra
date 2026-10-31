{ lib, ... }:
let
  asn = 395388;
  routerId = "199.255.18.181";
  uplinkV6 = "2606:7940:32:3c::11";

  prefixes = {
    ipv4 = [ "23.190.72.0/24" ];
    ipv6 = [ "2620:c2:2000::/48" ];
  };

  prefixSet = family: "[ ${lib.concatStringsSep ", " prefixes.${family}} ]";
  staticRoutes =
    family: lib.concatMapStrings (p: "  route ${p} blackhole;\n") prefixes.${family};

  rtrPort = 3323;
in
{
  # local RPKI validator, bird talks RTR to it. state lands in
  # /var/lib/private/routinator (DynamicUser) which impermanence already keeps.
  services.routinator = {
    enable = true;
    settings.rtr-listen = [ "127.0.0.1:${toString rtrPort}" ];
    # /status (per-repo fetch times, vrp counts) and /metrics. localhost only,
    # curl it over ssh
    settings.http-listen = [ "127.0.0.1:8323" ];
  };

  # bird instead of gobgp: gobgp starved keepalives while dumping the full
  # table to bgp.tools and died at the 90s hold timer every time, then
  # reconnected every ~2s with no backoff until bgp.tools kicked us.
  #
  # there is deliberately NO `protocol kernel` here. nothing bird learns gets
  # anywhere near the FIB, so the spectrum ASIC only ever sees the static
  # routes from network.nix. full tables live in bird's RIB and that's it.
  services.bird = {
    enable = true;
    config = ''
      log syslog all;
      router id ${routerId};

      protocol device {
        scan time 10;
      }

      # our own prefixes, originated from here. blackhole is fine since they
      # never get exported to the kernel.
      protocol static static4 {
        ipv4;
      ${staticRoutes "ipv4"}}

      protocol static static6 {
        ipv6;
      ${staticRoutes "ipv6"}}

      roa4 table rpki4;
      roa6 table rpki6;

      # if routinator goes away the ROAs expire and everything turns NotFound,
      # i.e. we fail open and keep accepting.
      protocol rpki routinator {
        roa4 { table rpki4; };
        roa6 { table rpki6; };
        remote 127.0.0.1 port ${toString rtrPort};
        # only matters while the session is down. the 600s default meant every
        # routinator restart left us without updates for 10 minutes
        retry keep 30;
      }

      # drop invalids, keep valid + notfound. on 2026-10-30 that was ~100 of
      # 1.3M prefixes, a third of them re-originated by 174 itself.
      filter cofractal_in4 {
        if roa_check(rpki4) = ROA_INVALID then reject;
        accept;
      }

      filter cofractal_in6 {
        if roa_check(rpki6) = ROA_INVALID then reject;
        accept;
      }

      filter cofractal_out4 {
        if source = RTS_STATIC && net ~ ${prefixSet "ipv4"} then accept;
        reject;
      }

      filter cofractal_out6 {
        if source = RTS_STATIC && net ~ ${prefixSet "ipv6"} then accept;
        reject;
      }

      template bgp cofractal {
        local ${uplinkV6} as ${toString asn};

        # RFC 5549: ipv4 routes with an ipv6 nexthop over the ipv6 session.
        # next hop self picks the session source, i.e. ${uplinkV6}.
        #
        # import table keeps the pre-filter routes around, so when the ROAs
        # change bird re-runs the filter on just the affected prefixes instead
        # of asking cofractal for a full route refresh every time.
        ipv4 {
          extended next hop on;
          import table on;
          import filter cofractal_in4;
          export filter cofractal_out4;
          next hop self;
        };

        ipv6 {
          import table on;
          import filter cofractal_in6;
          export filter cofractal_out6;
          next hop self;
        };
      }

      protocol bgp cofractal1 from cofractal {
        neighbor 2606:7940:32:3c::2 as 26073;
      }

      protocol bgp cofractal2 from cofractal {
        neighbor 2606:7940:32:3c::3 as 26073;
      }

      # full table feed. bgp.tools sends us nothing useful, we send them
      # everything we have.
      protocol bgp bgptools {
        local ${routerId} as ${toString asn};
        neighbor 185.230.223.73 as 212232;
        multihop;

        ipv4 {
          import none;
          export all;
          next hop self;
        };

        # ipv6 over an ipv4 session needs an explicit v6 nexthop
        ipv6 {
          import none;
          export all;
          next hop address ${uplinkV6};
        };
      }
    '';
  };
}
