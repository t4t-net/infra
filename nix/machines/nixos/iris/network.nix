{ config, lib, ... }:
let
  mark = "0xca6c";
  table = "51820";

  # tailscale's own rules sit at 5210-5270, so th tailnet nd its bypass-marked packets never get this
  # far nd keep using th droplet's uplink. everything else leaves as 23.190.72.254, nd if th tunnel is
  # down it goes nowhere instead of falling back 2 th digitalocean address
  rules = [
    "priority 5281 lookup main suppress_prefixlength 0" # on-link stuff, but not th default route
    "priority 5282 not fwmark ${mark} lookup ${table}"
  ];
  rules4 = [ "priority 5280 to 169.254.169.254 lookup main" ] ++ rules; # th droplet metadata service

  ipRules =
    verb: suffix:
    lib.concatMapStrings (rule: "ip -4 rule ${verb} ${rule}${suffix}\n") rules4
    + lib.concatMapStrings (rule: "ip -6 rule ${verb} ${rule}${suffix}\n") rules;
  delRules = ipRules "del" " 2>/dev/null || true";
in
{
  sops.secrets."wireguard/private-key" = {
    sopsFile = ./secrets/wireguard.yaml;
    key = "private-key";
  };

  # th scripted module, cuz this box is dhcpcd + tailscale nd turning on networkd would have it
  # fighting them over routes nd rules
  networking.wireguard.interfaces.wg-t4t = {
    privateKeyFile = config.sops.secrets."wireguard/private-key".path;
    ips = [
      "23.190.72.254/32"
      "2620:c2:2000:2::1/128"
    ];
    mtu = 1420;
    inherit table;
    fwMark = mark;

    peers = [
      {
        name = "peer2peer";
        publicKey = "sa/daVZL8671vKjrhHVJlAzm94owuY3w6wFlXEYpC0g=";
        endpoint = "23.190.72.45:51821";
        allowedIPs = [
          "0.0.0.0/0"
          "::/0"
        ];
        persistentKeepalive = 25;
      }
    ];

    preSetup = delRules;
    postSetup = ipRules "add" "";
    postShutdown = delRules;
  };
}
