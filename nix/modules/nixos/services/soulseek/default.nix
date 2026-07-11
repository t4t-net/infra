{ config, ... }:
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/slskd;
        mode = "0770";
        owner = "slskd";
        group = "slskd";
      }
    ];

    sops.secrets."services/soulseek/environment" = {
      sopsFile = ./secrets.yaml;
    };

    services.slskd.enable = true;
    services.slskd.openFirewall = true;
    services.slskd.settings = {
      soulseek.description = ''
        A TRANS PERSON PEED HERE!!

        The Industrial Revolution and its consequences have been a disaster for the human race.
        They have greatly increased the life-expectancy of those of us who live in “advanced” countries,
        but they have destabilized society, have made life unfulfilling, have subjected human beings to indignities,
        have led to widespread psychological suffering (in the Third World to physical suffering as well) and have inflicted severe damage on the natural world.
        The continued development of technology will worsen the situation.
        It will certainly subject human beings to greater indignities and inflict greater damage on the natural world,
        it will probably lead to greater social disruption and psychological suffering,
        and it may lead to increased physical suffering even in “advanced” countries.

        catgirl infrastructure witch
        proud polyam anarchist tranny
        militant nixos user
        served off of AS395388 (t4t.net) with a dual 25GbE connection
        source is Bandcamp / Tidal / other Soulseek users

        !! this system is headless and unmonitored. chats will likely go ignored. email me at soulseek@t4t.net instead !!

        xoxo,
        kitty
      '';
      soulseek.picture = ./picture.jpg;
      shares.directories = [
        "/media/music"
      ];
      directories.downloads = "/media/downloads/slskd/complete";
      directories.incomplete = "/media/downloads/slskd/incomplete";
    };
    services.slskd.domain = "slskd.tail09d5b.ts.net";
    services.slskd.environmentFile = config.sops.secrets."services/soulseek/environment".path;
    services.slskd.nginx.listenAddresses = [ "127.0.0.1" ];

    systemd.services.slskd.serviceConfig.UMask = "000";

    users.groups.slskd.members = [
      "lidarr"
    ];

    rv32ima.machine.tailscale.services.slskd = {
      port = 5030;
    };
  };
}
