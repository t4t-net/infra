{ config, ... }:
let
  port = 3739;

  # both halves r load-bearing!! hermes silently swaps a model.base_url back 2 th real api unless th
  # path ends in /anthropic, nd anything w/o "anthropic.com" in th url counts as a third party relay,
  # which strips her signed thinking on every turn. recheck both on every hermes bump
  prefix = "/api.anthropic.com/anthropic";

  # nginx only verifies upstream tls if u ask, nd this is th thing holding th real key
  upstream = ''
    include ${config.sops.templates."anthropic-proxy/key.conf".path};
    proxy_set_header Authorization "";
    proxy_set_header Host api.anthropic.com;
    proxy_set_header Connection "";
    proxy_http_version 1.1;
    proxy_ssl_server_name on;
    proxy_ssl_name api.anthropic.com;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 900s;
  '';
in
{
  config = {
    # th raw key, not a dotenv line. deliberately not in hermes/env, thats readable from th container.
    # it can use this proxy all it wants, it just cant walk off w th key
    sops.secrets."anthropic-proxy/api-key" = {
      sopsFile = ../../../machines/nixos/iris/secrets/anthropic-proxy.yaml;
      key = "api-key";
    };

    # a template cuz nginx's own config lands in th store
    sops.templates."anthropic-proxy/key.conf" = {
      content = ''
        proxy_set_header x-api-key "${config.sops.placeholder."anthropic-proxy/api-key"}";
      '';
      owner = config.services.nginx.user;
      restartUnits = [ "nginx.service" ];
    };

    systemd.services.nginx.before = [ "hermes-agent.service" ];

    services.nginx = {
      enable = true;
      clientMaxBodySize = "32m";
      # a plain proxy_pass resolves once at startup nd then holds that ip 4ever. a spoofed answer cant
      # get th key either, upstream tls is verified against api.anthropic.com
      resolver.addresses = [
        "1.1.1.1"
        "1.0.0.1"
      ];
      upstreams.anthropic = {
        servers."api.anthropic.com:443".resolve = true;
        extraConfig = "zone anthropic 64k;";
      };
      # only wat hermes calls, so a stolen foothold cant reach files or batches thru th real key
      virtualHosts."anthropic-proxy" = {
        listen = [
          {
            addr = "127.0.0.1";
            inherit port;
          }
        ];
        locations = {
          "= ${prefix}/v1/messages" = {
            proxyPass = "https://anthropic/v1/messages";
            extraConfig = upstream;
          };
          "= ${prefix}/v1/messages/count_tokens" = {
            proxyPass = "https://anthropic/v1/messages/count_tokens";
            extraConfig = upstream;
          };
          "${prefix}/v1/models" = {
            proxyPass = "https://anthropic/v1/models";
            extraConfig = upstream;
          };
        };
      };
    };

    services.hermes-agent = {
      # not a secret, it only has 2 look right: hermes wants a key 2 exist, nd any other sk-ant- prefix
      # gets treated as oauth. if something dodges th base_url it 401s instead of leaking anything
      environment.ANTHROPIC_API_KEY = "sk-ant-api03-iris-placeholder";
      settings.model.base_url = "http://127.0.0.1:${toString port}${prefix}";
    };
  };
}
