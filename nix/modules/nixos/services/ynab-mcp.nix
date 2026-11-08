{
  config,
  lib,
  pkgs,
  ...
}:
let
  port = 3740;
in
{
  config = {
    # th oauth app's client id + secret. th refresh token isnt in sops, it may rotate on every
    # refresh, so it lives in th unit's state dir. ellie connects it thru iris (ynab_auth_start),
    # or w packages/ynab-mcp/bootstrap.sh if iris herself is broken
    sops.secrets = lib.genAttrs [ "ynab-mcp/client_id" "ynab-mcp/client_secret" ] (name: {
      sopsFile = ../../../machines/nixos/iris/secrets/ynab-mcp.yaml;
      key = lib.removePrefix "ynab-mcp/" name;
    });

    # not in hermes/env, cuz thats readable from her container
    sops.templates."ynab-mcp/env" = {
      content = ''
        YNAB_CLIENT_ID=${config.sops.placeholder."ynab-mcp/client_id"}
        YNAB_CLIENT_SECRET=${config.sops.placeholder."ynab-mcp/client_secret"}
      '';
      restartUnits = [ "ynab-mcp.service" ];
    };

    # same shape as hevy-mcp: on th host, loopback, no bearer token. th grant is read-only at ynab's
    # end, so even th tokens leaking would only leak reads
    systemd.services.ynab-mcp = {
      description = "read-only ynab mcp server 4 iris";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      before = [ "hermes-agent.service" ];
      wantedBy = [ "multi-user.target" ];
      environment = {
        # also wat ynab_auth_finish checks a new grant against, so a code from some other account
        # cant swap her budget out
        YNAB_PLAN_ID = "ec9354a8-6402-409b-9b27-667d0c119ac3";
        # has 2 match th oauth app, nd bootstrap.sh's default
        YNAB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob";
      };
      serviceConfig = {
        ExecStart = "${lib.getExe pkgs.rv32ima.ynab-mcp} --host 127.0.0.1 --port ${toString port}";
        EnvironmentFile = config.sops.templates."ynab-mcp/env".path;
        Restart = "on-failure";
        DynamicUser = true;
        StateDirectory = "ynab-mcp";
        StateDirectoryMode = "0700";
        UMask = "0077";
        ProtectHome = true;
        PrivateDevices = true;
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
        ];
      };
    };

    services.hermes-agent.mcpServers.ynab = {
      url = "http://127.0.0.1:${toString port}/mcp";
      tools.include = [
        "list_plans"
        "get_accounts"
        "get_month"
        "list_months"
        "find_payees"
        "get_transactions"
        "get_scheduled_transactions"
        "ynab_auth_start"
        "ynab_auth_finish"
      ];
    };
  };
}
