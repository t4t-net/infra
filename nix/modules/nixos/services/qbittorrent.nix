{ ... }:
let
  torrentingPort = 50000;
  webuiPort = 8080;
  downloadDir = "/media/downloads/qbittorrent";
in
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/qBittorrent;
        mode = "0750";
        owner = "qbittorrent";
        group = "qbittorrent";
      }
    ];

    services.qbittorrent = {
      enable = true;
      inherit torrentingPort webuiPort;
    };
    services.qbittorrent.serverConfig = {
      LegalNotice.Accepted = true;
      BitTorrent.Session = {
        DefaultSavePath = downloadDir;
        Port = torrentingPort;
        MaxConnections = 4000;
        MaxConnectionsPerTorrent = 200;
        MaxUploads = 400;
        MaxActiveDownloads = 20;
        MaxActiveTorrents = -1;
        MaxActiveUploads = -1;
        QueueingSystemEnabled = false;
      };
      Preferences.WebUI = {
        # Only reachable thru tailscale serve, which proxies from localhost,
        # so let the tailnet (and the *arrs) in without a password like rutorrent did
        Address = "127.0.0.1";
        LocalHostAuth = false;
        ServerDomains = "qbittorrent.tail09d5b.ts.net;localhost;127.0.0.1";
      };
    };

    systemd.services.qbittorrent.serviceConfig = {
      # Match rtorrent's umask so the *arrs can pick up completed downloads
      UMask = "0000";
      LimitNOFILE = "262144";
    };

    systemd.tmpfiles.rules = [
      "d ${downloadDir} 0777 qbittorrent qbittorrent -"
    ];

    # The upstream openFirewall only does TCP, and we want uTP/DHT too
    networking.firewall.allowedTCPPorts = [ torrentingPort ];
    networking.firewall.allowedUDPPorts = [ torrentingPort ];

    rv32ima.machine.tailscale.services.qbittorrent = {
      port = webuiPort;
    };
  };
}
