{
  config,
  lib,
  pkgs,
  ...
}:
let
  port = 3737;
in
{
  config = {
    # HEVY_API_KEY as a dotenv line. deliberately not in hermes/env, that lands in .env inside
    # hermes' state dir, nd th whole dir is mounted in th container she runs commands in
    sops.secrets."hevy-mcp/env" = {
      sopsFile = ../../../machines/nixos/iris/secrets/hevy-mcp.yaml;
      key = "env";
      restartUnits = [ "hevy-mcp.service" ];
    };

    # on th host so th key stays out of th container. loopback w no bearer token, cuz th build has
    # no write tools nd a token would only end up in that same .env
    systemd.services.hevy-mcp = {
      description = "read-only hevy mcp server 4 iris";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      before = [ "hermes-agent.service" ];
      wantedBy = [ "multi-user.target" ];
      environment.HEVY_MCP_TELEMETRY = "0";
      serviceConfig = {
        ExecStart = "${lib.getExe pkgs.rv32ima.hevy-mcp} --transport http --host 127.0.0.1 --port ${toString port}";
        EnvironmentFile = config.sops.secrets."hevy-mcp/env".path;
        Restart = "on-failure";
        DynamicUser = true;
        ProtectHome = true;
        PrivateDevices = true;
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
        ];
      };
    };

    # th server is already read-only, this is just th second layer. --network=host is wat lets th
    # container reach loopback
    services.hermes-agent.mcpServers.hevy = {
      url = "http://127.0.0.1:${toString port}/mcp";
      tools.include = [
        "get-training-summary"
        "get-workouts"
        "get-workout"
        "get-workout-events"
        "search-routines"
        "get-routines"
        "get-routine"
        "get-routine-folder"
        "get-exercise-template"
        "search-exercise-templates"
        "get-exercise-history"
        "get-body-measurements"
        "get-body-measurement"
      ];
    };
  };
}
