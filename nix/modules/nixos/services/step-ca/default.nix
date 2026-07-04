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
        x509Template = pkgs.writeText "x509.tpl" ''
          {
              "subject": {{ toJson .Subject }},
              "sans": {{ toJson .SANs }},
          {{- if typeIs "*rsa.PublicKey" .Insecure.CR.PublicKey }}
              "keyUsage": ["keyEncipherment", "digitalSignature"],
          {{- else }}
              "keyUsage": ["digitalSignature"],
          {{- end }}
              "extKeyUsage": ["serverAuth", "clientAuth"]
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
        githubActionsSSHTemplate = pkgs.writeText "github-actions-ssh.tpl" ''
          {{- if not (eq .Token.sub "repo:rv32ima/dotfiles:ref:refs/heads/main") -}}
          {{- fail "unauthorized: only rv32ima/dotfiles main branch is allowed" -}}
          {{- end -}}
          {
            "type": {{ toJson .Type }},
            "keyId": {{ toJson .Token.sub }},
            "principals": [ {{ toJson .Token.sub }} ],
            "extensions": {{ toJson .Extensions }},
            "criticalOptions": {{ toJson .CriticalOptions }}
          }
        '';
      in
      {
        authority = {
          provisioners = [
            {
              encryptedKey = "eyJhbGciOiJQQkVTMi1IUzI1NitBMTI4S1ciLCJjdHkiOiJqd2sranNvbiIsImVuYyI6IkEyNTZHQ00iLCJwMmMiOjYwMDAwMCwicDJzIjoid3FmT2w4Q3hldjhZeXhKQkJzdTVCdyJ9.kUyoE8KhDYII89gxRt4jHNhVNTd3ghXrKO1brT2a3zeR6VFSFgOPDA.RYlJM1hW00E4puL0.JvpEODq_yKWeHZmkv1f4pdkKsXKslnf-Z6F4mG3u4uGKqcwhUvqpLKZ0UWiMT-fHl4RekRi4XA7F_67jPqwyuvwamzRhzyfwgqLorEBs9mPZRD0AizF2RURol-kOzJHMxF6vKNWHkFuF3TKi56IvgoapQWB-AMD4hHheDWYoAL0BifR1GVGiIkBdeH7LKLve8sWk2HiOE41kX-y19zMZgmDH499JgOzV0q16-ImBXG7hSivQz18mQOQ2kkGX88DiPXwa_eg_tqmmI0tPP9oFWlRgP8D4f7aelPn0fcdy2vhm4Ik43TgRO2-U40Z3Xyq5RLOfJBiYoKiB-ztCOMU.eKW5Lv9M6FK7txhhsx22uw";
              key = {
                alg = "ES256";
                crv = "P-256";
                kid = "c83DXf8QpGr9dPE4tUWEWzIoydCTzWFqmsuZ2BTw4eE";
                kty = "EC";
                use = "sig";
                x = "l2YMYC2LVDRkOpHlCblby7-1ZHPutunJ_WW4HlAtR80";
                y = "QuAqRVFR32V28Zjw9TjopM2Ifh-jJ6sz94F0s1VeqSk";
              };
              name = "ellie@t4t.net";
              type = "JWK";
              claims = {
                enableSSHCA = true;
              };
            }
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
                  templateFile = "${x509Template}";
                };
                ssh = {
                  templateFile = "${sshTemplate}";
                };
              };
            }
            {
              type = "OIDC";
              name = "github-actions";
              clientID = "https://ca.t4t.net";
              configurationEndpoint = "https://token.actions.githubusercontent.com/.well-known/openid-configuration";
              claims = {
                enableSSHCA = true;
                maxTLSCertDuration = "1h";
                defaultTLSCertDuration = "1h";
                disableRenewal = true;
              };
              options = {
                ssh = {
                  templateFile = "${githubActionsSSHTemplate}";
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
                  templateFile = "${sshTemplate}";
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
