{ config, inputs, ... }:
let
  llamaUrl = "http://experimental-skin.tail09d5b.ts.net:8080/v1";
  ellie = "130951003100020736";
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

    # hermes only reads .env at startup, nd th module rewrites it w/o touching th unit, so a config
    # change would otherwise sit there until th next reboot
    systemd.services.hermes-agent.restartTriggers = [
      (builtins.toJSON config.services.hermes-agent.environment)
      (builtins.toJSON config.services.hermes-agent.settings)
      config.services.hermes-agent.hermesHomeFiles."SOUL.md"
    ];

    services.hermes-agent = {
      enable = true;

      hermesHomeFiles."SOUL.md" = ../../../machines/nixos/iris/SOUL.md;

      environmentFiles = [ config.sops.secrets."hermes/env".path ];
      environment = {
        # hermes only sends OPENAI_API_KEY 2 this exact origin
        OPENAI_BASE_URL = llamaUrl;
        # default-deny, this is ellie nd nobody else
        DISCORD_ALLOWED_USERS = ellie;
        # so luna can @ her in a thread. careful: bots skip DISCORD_ALLOWED_USERS entirely, so any bot
        # in a server she shares can do this too. keep her in private servers only!!
        DISCORD_ALLOW_BOTS = "mentions";
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
        # bots skip th allowlist nd a typed /approve runs a pending command, tested it!! gating slash
        # commands 2 ellie means luna (or any other bot) can talk 2 her but not approve anything
        gateway.platforms.discord.extra = {
          allow_admin_from = [ ellie ];
          group_allow_admin_from = [ ellie ];
          user_allowed_commands = [ ];
          group_user_allowed_commands = [ ];
        };
      };
    };
  };
}
