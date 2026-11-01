{
  pkgs,
  config,
  ...
}:
let
  configContent = builtins.toJSON (
    config.services.step-ca.settings
    // {
      address = config.services.step-ca.address + ":" + toString config.services.step-ca.port;
    }
  );
in
{
  config = {
    sops.templates."services/step-ca/config" = {
      content = configContent;
      owner = "step-ca";
      group = "step-ca";
      mode = "0400";
    };

    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/postgresql;
        mode = "0700";
        owner = "postgres";
        group = "postgres";
      }
    ];

    sops.secrets."services/step-ca/environment" = {
      sopsFile = ./secrets.yaml;
    };

    sops.secrets."services/step-ca/google-oauth/client-id" = {
      sopsFile = ./secrets.yaml;
    };

    sops.secrets."services/step-ca/google-oauth/client-secret" = {
      sopsFile = ./secrets.yaml;
    };

    systemd.services."step-ca" = {
      wantedBy = [ "multi-user.target" ];
      restartTriggers = [ configContent ];
      unitConfig = {
        ConditionFileNotEmpty = ""; # override upstream
      };
      serviceConfig = {
        User = "step-ca";
        Group = "step-ca";
        UMask = "0077";
        Environment = "HOME=%S/step-ca";
        EnvironmentFile = config.sops.secrets."services/step-ca/environment".path;
        WorkingDirectory = ""; # override upstream
        ReadWritePaths = ""; # override upstream
        AmbientCapabilities = "CAP_NET_BIND_SERVICE";
        CapabilityBoundingSet = "CAP_NET_BIND_SERVICE";

        ExecStart = [
          "" # override upstream
          "${pkgs.step-ca}/bin/step-ca ${config.sops.templates."services/step-ca/config".path}"
        ];

        # ProtectProc = "invisible"; # not supported by upstream yet
        # ProcSubset = "pid"; # not supported by upstream yet
        # PrivateUsers = true; # doesn't work with privileged ports therefore not supported by upstream

        DynamicUser = true;
        StateDirectory = "step-ca";
      };
    };

    users.users.step-ca = {
      home = "/var/lib/private/step-ca";
      group = "step-ca";
      isSystemUser = true;
    };

    users.groups.step-ca = { };

    services.step-ca.port = 443;
    services.step-ca.address = "0.0.0.0";
    services.step-ca.settings =
      let
        rootCA = ../../../../../certificates/root-ca.crt;
        intermediateCA = ../../../../../certificates/intermediate-ca.crt;
        # x5c takes its sans from th token, not th leaf, so any host could mint a leaf 4 another
        # host's name nd then get that host's ssh cert. nothing needs x509 from x5c, so it gets none
        x5cX509Template = pkgs.writeText "x5c-x509.tpl" ''
          {{- fail "unauthorized: x5c only signs ssh host certificates" -}}
        '';
        # x5c puts .Type nd .Principals in th token, nd whoever holds a leaf writes th token. so
        # without this any leaf could mint a user cert 4 "ellie". a host gets th names on its leaf,
        # plus their first label cuz ssh'ing 2 a short name checks th cert 4 that (no san has it nd
        # acme couldnt validate one). wildcards r skipped, th first label of *.t4t.net is "*"
        x5cSSHTemplate = pkgs.writeText "x5c-ssh.tpl" ''
          {{- if ne .Type "host" -}}
          {{- fail "unauthorized: x5c only signs ssh host certificates" -}}
          {{- end -}}
          {{- $allowed := list -}}
          {{- range .AuthorizationCrt.DNSNames -}}
          {{- if not (contains "*" .) -}}
          {{- $allowed = append $allowed . -}}
          {{- $allowed = append $allowed (first (splitList "." .)) -}}
          {{- end -}}
          {{- end -}}
          {{- range .Principals -}}
          {{- if not (has . $allowed) -}}
          {{- fail "unauthorized: ssh principal isnt on th x5c leaf" -}}
          {{- end -}}
          {{- end -}}
          {
            "type": {{ toJson .Type }},
            "keyId": {{ toJson .KeyID }},
            "principals": {{ toJson .Principals }},
            "extensions": {{ toJson .Extensions }},
            "criticalOptions": {{ toJson .CriticalOptions }}
          }
        '';
        sshTemplate = pkgs.writeText "ssh.tpl" ''
          {
            "type": {{ toJson .Type }},
            "keyId": {{ toJson .KeyID }},
            "principals": {{ toJson .Principals }},
            "extensions": {{ toJson .Extensions }},
            "criticalOptions": {{ toJson .CriticalOptions }}
          }
        '';
        # github's org ssh CA maps certs 2 users via the login@github.com extension,,
        # keep the email -> login mapping explicit so nobody else on ellie.fm can claim rv32ima
        googleSSHTemplate = pkgs.writeText "google-ssh.tpl" ''
          {{- $ext := dict -}}
          {{- range $k, $v := .Extensions }}{{ $_ := set $ext $k $v }}{{ end -}}
          {{- if eq .Token.email "me@ellie.fm" }}{{ $_ := set $ext "login@github.com" "rv32ima" }}{{ end -}}
          {
            "type": {{ toJson .Type }},
            "keyId": {{ toJson .KeyID }},
            "principals": {{ toJson .Principals }},
            "extensions": {{ toJson $ext }},
            "criticalOptions": {{ toJson .CriticalOptions }}
          }
        '';
      in
      {
        authority = {
          provisioners = [
            {
              type = "ACME";
              name = "acme";
              forceCN = true;
              claims = {
                maxTLSCertDuration = "8760h";
                defaultTLSCertDuration = "8760h";
              };
              termsOfService = "";
              website = "";
              caaIdentities = [ ];
              challenges = [
                "http-01"
                "dns-01"
                "tls-alpn-01"
              ];
            }
            {
              type = "SSHPOP";
              name = "sshpop";
              claims = {
                enableSSHCA = true;
              };
              options = {
                ssh = {
                  templateFile = "${sshTemplate}";
                };
              };
            }
            {
              type = "X5C";
              name = "x5c";
              roots =
                let
                  roots = [
                    (builtins.readFile "${rootCA}")
                    (builtins.readFile "${intermediateCA}")
                  ];
                  rootsStr = pkgs.lib.strings.concatStrings roots;
                in
                pkgs.lib.toBase64 rootsStr;
              claims = {
                maxTLSCertDuration = "8h";
                defaultTLSCertDuration = "2h";
                disableRenewal = true;
                enableSSHCA = true;
              };
              options = {
                x509 = {
                  templateFile = "${x5cX509Template}";
                };
                ssh = {
                  templateFile = "${x5cSSHTemplate}";
                };
              };
            }
            {
              type = "OIDC";
              name = "google";
              clientID = "${config.sops.placeholder."services/step-ca/google-oauth/client-id"}";
              clientSecret = "${config.sops.placeholder."services/step-ca/google-oauth/client-secret"}";
              configurationEndpoint = "https://accounts.google.com/.well-known/openid-configuration";
              admins = [ "me@ellie.fm" ];
              domains = [ "ellie.fm" ];
              scopes = [
                "openid"
                "email"
              ];
              claims = {
                enableSSHCA = true;
                maxTLSCertDuration = "24h";
                defaultTLSCertDuration = "24h";
                disableRenewal = true;
              };
              options = {
                ssh = {
                  templateFile = "${googleSSHTemplate}";
                };
              };
            }
          ];

          policy = {
            x509 = {
              allow = {
                dns = [
                  "*.t4t.net"
                  "*.sea.t4t.net"
                  "*.tail09d5b.ts.net"
                  "*.sfo.t4t.net"
                ];
              };
              allowWildcardNames = true;
            };
          };
        };
        crt = "${intermediateCA}";
        db = {
          dataSource = "postgresql://step-ca?host=/run/postgresql";
          database = "step-ca";
          type = "postgresql";
        };
        dnsNames = [ "ca.t4t.net" ];
        federatedRoots = null;
        insecureAddress = "";
        key = "awskms:key-id=e21f49a2-ef9f-4e87-9291-f5796f88727e";
        logger = {
          format = "text";
        };
        root = "${rootCA}";
        ssh = {
          hostKey = "awskms:key-id=f4f61975-422d-4f32-be56-33fe4a478b8e";
          userKey = "awskms:key-id=a369ada2-91e7-40fa-a40d-97b4613585cd";
        };
        kms = {
          type = "awskms";
          uri = "awskms:region=us-west-2";
        };
        tls = {
          cipherSuites = [
            "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256"
            "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256"
          ];
          maxVersion = 1.3;
          minVersion = 1.2;
          renegotiation = false;
        };
      };

    services.postgresql.enable = true;
    services.postgresql.ensureDatabases = [ "step-ca" ];
    services.postgresql.ensureUsers = [
      {
        name = "step-ca";
        ensureDBOwnership = true;
      }
    ];

    networking.firewall.allowedTCPPorts = [
      config.services.step-ca.port
    ];

  };
}
