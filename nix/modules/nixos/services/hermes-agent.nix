{ config, inputs, ... }:
let
  llamaUrl = "http://experimental-skin.tail09d5b.ts.net:8080/v1";
in
{
  imports = [
    inputs.hermes-agent.nixosModules.default
  ];

  config = {
    # DISCORD_BOT_TOKEN + OPENAI_API_KEY as dotenv lines
    sops.secrets."hermes/env" = {
      sopsFile = ../../../machines/nixos/iris/secrets/hermes.yaml;
      key = "env";
      restartUnits = [ "hermes-agent.service" ];
    };

    services.hermes-agent = {
      enable = true;

      environmentFiles = [ config.sops.secrets."hermes/env".path ];
      environment = {
        # hermes only sends OPENAI_API_KEY 2 this exact origin
        OPENAI_BASE_URL = llamaUrl;
        # default-deny, this is ellie nd nobody else
        DISCORD_ALLOWED_USERS = "130951003100020736";
      };

      # th whole agent lives in a container nd not just its terminal: terminal.backend = docker
      # skips dangerous-command approvals, nd those buttons r wat stands between a prompt injection
      # nd a bad day
      container.enable = true;

      settings = {
        model = {
          provider = "custom";
          base_url = llamaUrl;
          default = "qwen3.8-flash-next";
        };
        # smart mode asks a model whether a command is safe, nd th model is wat we dont trust here
        approvals.mode = "manual";
      };
    };
  };
}
