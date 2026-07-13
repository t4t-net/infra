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
        served to u with love from pawpatch

        TWO TRANS PEOPLE PEED HERE!!!
      '';
      shares.directories = [
        "/media/music"
      ];
      directories.downloads = "/media/downloads/slskd/complete";
      directories.incomplete = "/media/downloads/slskd/incomplete";
    };
    services.slskd.domain = "pawpatch-slskd.tail09d5b.ts.net";
    services.slskd.environmentFile = config.sops.secrets."services/soulseek/environment".path;
    services.slskd.nginx.listenAddresses = [ "127.0.0.1" ];

    systemd.services.slskd.serviceConfig.UMask = "000";

    rv32ima.machine.tailscale.services.pawpatch-slskd = {
      targetUnit = "slskd.service";
      port = 5030;
    };
  };
}
