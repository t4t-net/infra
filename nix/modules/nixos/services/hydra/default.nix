{
  config,
  lib,
  pkgs,
  ...
}:
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/hydra;
        mode = "0770";
        owner = "hydra";
        group = "hydra";
      }
      {
        path = /var/lib/postgresql;
        mode = "0770";
        owner = "postgres";
        group = "postgres";
      }
    ];

    sops.secrets."services/hydra/r2" = {
      sopsFile = ./secrets.yaml;
      owner = "root";
      group = "root";
    };

    sops.secrets."services/hydra/smtp-password" = {
      sopsFile = ./secrets.yaml;
      owner = "root";
      group = "root";
    };

    sops.secrets."services/hydra/nix-signing-key" = {
      sopsFile = ./secrets.yaml;
      owner = "hydra-queue-runner";
      group = "nogroup";
    };

    services.hydra = {
      enable = true;
      hydraURL = "https://hydra.tail09d5b.ts.net";
      notificationSender = "hydra@t4t.net";
      buildMachinesFiles = [ "/etc/nix/machines" ];
      useSubstitutes = true;
      smtpHost = "smtp.fastmail.com";
      # max_db_connections caps the queue-runner's connection pool (hydra defaults it to 128, more
      # than postgres allows in total). one per build slot is plenty
      extraConfig = ''
        store_uri = s3://rv32ima-nix-store?secret-key=${
          config.sops.secrets."services/hydra/nix-signing-key".path
        }&endpoint=359f72dd5610ef51b6f186e0818ab188.r2.cloudflarestorage.com&region=auto&compression=zstd
        max_db_connections = 64
      '';
    };

    # worst case for hydra: queue-runner 64 + hydra-server 25 (maxServers) + evaluator ~6 + notify/stats 2.
    # postgres' default of 100 (97 after superuser reservations) got exhausted
    services.postgresql.settings.max_connections = 150;

    sops.templates."services/hydra/smtp" = {
      content = ''
        EMAIL_SENDER_TRANSPORT_sasl_username=me@ellie.fm
        EMAIL_SENDER_TRANSPORT_sasl_password=${config.sops.placeholder."services/hydra/smtp-password"}
        EMAIL_SENDER_TRANSPORT_port=587
        EMAIL_SENDER_TRANSPORT_ssl=starttls
      '';
    };

    systemd.services.hydra-notify = {
      serviceConfig.EnvironmentFile = "${config.sops.templates."services/hydra/smtp".path}";
    };

    systemd.services.hydra-queue-runner = {
      serviceConfig.EnvironmentFile = "${config.sops.secrets."services/hydra/r2".path}";
    };

    # the queue runner spawns ssh to remote builders as hydra-queue-runner, not root, so it has
    # to own the builder key. root's nix-daemon can still read it, and ssh only refuses loose
    # perms on keys owned by the calling user
    systemd.tmpfiles.rules = [
      "z /persist/etc/nix/builder_ed25519 0400 hydra-queue-runner root"
    ];

    rv32ima.machine.tailscale.services.hydra = {
      targetUnit = "hydra-server.service";
      port = 3000;
    };
  };
}
