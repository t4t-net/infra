{
  inputs,
  config,
  pkgs,
  self,
  ...
}:
let
  pkgsUnstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
  };
in
{
  imports = [
    (self.lib.nixosModule "nixos/impermanence")
    (self.lib.nixosModule "nixos/home-manager")
    (self.lib.nixosModule "nixos/update-dotfiles")
    (self.lib.nixosModule "nixos/remote-builder")
    (self.lib.nixosModule "nixos/bootstrapper")
    (self.lib.nixosModule "nixos/deploy")
    (self.lib.nixosModule "nixos/machine-certificate")
    (self.lib.nixosModule "nixos/services/soulseek")
    (self.lib.nixosModule "nixos/services/plex")
    (self.lib.nixosModule "nixos/services/rtorrent")
    (self.lib.nixosModule "nixos/services/radarr")
    (self.lib.nixosModule "nixos/services/lidarr")
    (self.lib.nixosModule "nixos/services/beets")
    (self.lib.nixosModule "nixos/services/sonarr")
    (self.lib.nixosModule "nixos/services/prowlarr")
    (self.lib.nixosModule "nixos/services/overseerr")
    (self.lib.nixosModule "nixos/services/unpackerr")
    (self.lib.nixosModule "nixos/services/tailscale")
    (self.lib.nixosModule "nixos/services/nzbget")
    (self.lib.nixosModule "nixos/services/copyparty")
    (self.lib.nixosModule "nixos/services/soularr")

    (self.lib.nixosModule "users/root")
    (self.lib.nixosModule "users/ellie")

    ./network.nix
    ./disk-config.nix
  ];

  config = {
    rv32ima.machine.impermanence.enable = true;
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/sbctl;
        mode = "0644";
        owner = "root";
        group = "root";
      }
    ];

    rv32ima.machine.bootstrapper.baseUrl = "http://peer2peer.sea.t4t.net:8787";

    boot.loader.limine.enable = true;
    boot.loader.limine.secureBoot.enable = true;
    boot.loader.limine.efiInstallAsRemovable = true;

    boot.initrd.availableKernelModules = [
      "ahci"
      "xhci_pci"
      "megaraid_sas"
      "usbhid"
      "usb_storage"
      "sd_mod"
      "sr_mod"
    ];
    boot.initrd.kernelModules = [ ];
    boot.kernelModules = [ "kvm-intel" ];
    boot.extraModulePackages = [ ];

    # head -c4 /dev/urandom | od -A none -t x4
    networking.hostId = "a41ae525";

    rv32ima.machine.tailscale.enable = true;

    services.prometheus.exporters.node.enable = true;

    services.openssh.enable = true;
    services.openssh.openFirewall = false;

    programs.fish.enable = true;
    programs.fish.useBabelfish = true;

    networking.useNetworkd = true;
    networking.firewall.allowedTCPPorts = [ ];
    networking.firewall.logRefusedConnections = false;

    sops.secrets."services/restic/media/password" = {
      sopsFile = ./secrets/restic.yaml;
      owner = config.users.users."restic".name;
      group = config.users.users."restic".group;
      mode = "0440";
    };

    sops.secrets."services/restic/media/rcloneConfig" = {
      sopsFile = ./secrets/restic.yaml;
      owner = config.users.users."restic".name;
      group = config.users.users."restic".group;
      mode = "0440";
    };

    users.users."restic" = {
      enable = true;
      group = "restic";
      isSystemUser = true;
    };

    services.restic.backups."media" = {
      repository = "rclone:secret:restic/media";
      user = config.users.users."restic".name;
      paths = [
        "/media"
      ];
      passwordFile = config.sops.secrets."services/restic/media/password".path;
      rcloneConfigFile = config.sops.secrets."services/restic/media/rcloneConfig".path;
    };

    services.prometheus.exporters.restic = {
      enable = true;
      repository = "rclone:secret:restic/media";
      rcloneConfigFile = config.sops.secrets."services/restic/media/rcloneConfig".path;
      passwordFile = config.sops.secrets."services/restic/media/password".path;
    };

    users.groups."restic".members = [
      "restic"
      "restic-exporter"
    ];

    sops.secrets."services/msmtp/password" = {
      sopsFile = ./secrets/msmtp.yaml;
      mode = "0444";
    };

    services.mail.sendmailSetuidWrapper.enable = true;

    programs.msmtp = {
      enable = true;
      setSendmail = true;
      defaults = {
        aliases = "/etc/aliases";
        port = 587;
        auth = "plain";
        tls = "on";
        tls_starttls = "on";
      };
      accounts.default = {
        host = "smtp.fastmail.com";
        passwordeval = "cat ${config.sops.secrets."services/msmtp/password".path}";
        from = "admin@t4t.net";
        user = "me@ellie.fm";
      };
    };

    environment.etc.aliases.text = ''
      root: admin@t4t.net
    '';

    services.zfs.autoScrub.enable = true;
    services.zfs.autoScrub.interval = "weekly";

    networking.domain = "sea.t4t.net";
    system.primaryUser = "ellie";
  };
}
