{
  config,
  pkgs,
  lib,
  ...
}:
let
  fqdn = "${config.networking.hostName}.${config.networking.domain}";
  tailnetFqdn = "${config.networking.hostName}.tail09d5b.ts.net";
  certDir = "/var/lib/acme/${fqdn}";
  rootCA = ../../../certificates/root-ca.crt;
  sshUserCA = ../../../certificates/ssh-user-ca.pub;
  caURL = "https://ca.t4t.net";

  # Host key path varies when impermanence moves keys to /persist/etc/ssh/
  ed25519HostKey = lib.findFirst (k: k.type == "ed25519") null config.services.openssh.hostKeys;
  sshHostKeyPath =
    if ed25519HostKey != null then ed25519HostKey.path else "/etc/ssh/ssh_host_ed25519_key";

in
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/acme;
        mode = "0755";
        owner = "acme";
        group = "acme";
      }
    ];

    security.acme.acceptTerms = true;
    security.acme.certs.${fqdn} = {
      email = "ellie@t4t.net";
      server = "https://ca.t4t.net/acme/acme/directory";
      extraDomainNames = [
        tailnetFqdn
      ];
      # When nginx owns port 80, step aside to a high port and let nginx proxy the challenge.
      listenHTTP = if config.services.nginx.enable then ":1360" else ":80";
    };

    networking.firewall.allowedTCPPorts = [ 80 ];

    # Proxy the ACME HTTP-01 challenge through nginx when it's present.
    services.nginx.virtualHosts.${fqdn} = lib.mkIf config.services.nginx.enable {
      locations."/.well-known/acme-challenge/" = {
        proxyPass = "http://127.0.0.1:1360";
        extraConfig = "proxy_set_header Host $host;";
      };
    };

    # Trust t4t.net SSH host certificates for all users on this machine.
    programs.ssh.knownHosts."t4t.net-ssh-ca" = {
      certAuthority = true;
      hostNames = [
        "*"
      ];
      publicKey = lib.fileContents ../../../certificates/ssh-host-ca.pub;
    };

    services.openssh.extraConfig = ''
      HostCertificate ${sshHostKeyPath}-cert.pub
    '';

    # Bootstrap SSH host certificate: exchange x509 cert (x5c) then immediately
    # renew via SSHPOP to get a full-duration cert. x5c issues short-lived certs
    # (8h max), SSHPOP renews to a standard duration. Runs at boot and on ACME renewal.
    systemd.services."machine-ssh-certificate" = {
      description = "Exchange machine x509 certificate for SSH host certificate";
      after = [ "acme-order-renew-${fqdn}.service" ];
      wants = [ "acme-order-renew-${fqdn}.service" ];
      wantedBy = [
        "multi-user.target"
        "acme-order-renew-${fqdn}.service"
      ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = pkgs.writeShellScript "machine-ssh-certificate" ''
          set -euo pipefail
          ${pkgs.step-cli}/bin/step ssh certificate \
            --host \
            --sign \
            --provisioner=x5c \
            --x5c-cert=${certDir}/fullchain.pem \
            --x5c-key=${certDir}/key.pem \
            --ca-url=${caURL} \
            --root=${rootCA} \
            --principal=${fqdn} \
            --principal=${config.networking.hostName} \
            --principal=${tailnetFqdn} \
            --force \
            ${fqdn} \
            ${sshHostKeyPath}.pub
          ${pkgs.step-cli}/bin/step ssh renew \
            --provisioner=sshpop \
            --ca-url=${caURL} \
            --root=${rootCA} \
            --force \
            ${sshHostKeyPath}-cert.pub \
            ${sshHostKeyPath}
          ${pkgs.systemd}/bin/systemctl reload sshd.service
        '';
      };
    };

    # Renew SSH host certificate via SSHPOP before it expires.
    systemd.timers."machine-ssh-certificate-renew" = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "15m";
        OnUnitActiveSec = "8h";
        RandomizedDelaySec = "10m";
      };
    };

    systemd.services."machine-ssh-certificate-renew" = {
      description = "Renew SSH host certificate via SSHPOP";
      unitConfig.ConditionPathExists = "${sshHostKeyPath}-cert.pub";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = pkgs.writeShellScript "machine-ssh-certificate-renew" ''
          set -euo pipefail
          ${pkgs.step-cli}/bin/step ssh renew \
            --provisioner=sshpop \
            --ca-url=${caURL} \
            --root=${rootCA} \
            --force \
            ${sshHostKeyPath}-cert.pub \
            ${sshHostKeyPath}
          ${pkgs.systemd}/bin/systemctl reload sshd.service
        '';
      };
    };
  };
}
