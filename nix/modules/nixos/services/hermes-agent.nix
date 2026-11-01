{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
let
  llamaUrl = "http://experimental-skin.tail09d5b.ts.net:8080/v1";
  ellie = "130951003100020736";

  # hermes hides its python set, but it takes uv2nix as an arg, so sneak our patch in thru th
  # workspace overlay. no fork, no ifd, nd only th hermes-agent wheel rebuilds. drop this once
  # upstream #146847 lands
  uv2nix = inputs.hermes-agent.inputs.uv2nix;
  patchedUv2nix = uv2nix // {
    lib = uv2nix.lib // {
      workspace = uv2nix.lib.workspace // {
        loadWorkspace =
          args:
          let
            workspace = uv2nix.lib.workspace.loadWorkspace args;
          in
          workspace
          // {
            mkPyprojectOverlay =
              overlayArgs:
              lib.composeExtensions (workspace.mkPyprojectOverlay overlayArgs) (
                _: prev: {
                  hermes-agent = prev.hermes-agent.overrideAttrs (old: {
                    patches = (old.patches or [ ]) ++ [ ./hermes-approve-admin-only.patch ];
                  });
                }
              );
          };
      };
    };
  };

  # pinned w hermes itself. this linkFarm is th allowlist: pointing external_dirs at optional-skills
  # would hand her godmode nd web-pentest 2
  irisSkills = pkgs.linkFarm "iris-skills" {
    unbroker = pkgs.applyPatches {
      name = "hermes-unbroker";
      src = "${inputs.hermes-agent}/optional-skills/security/unbroker";
      patches = [ ./hermes-unbroker-dotenv.patch ];
    };
  };
in
{
  imports = [
    inputs.hermes-agent.nixosModules.default
  ];

  config = {
    # DISCORD_BOT_TOKEN + OPENAI_API_KEY + EMAIL_PASSWORD + FIRECRAWL_API_KEY as dotenv lines
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

    # skills call plain `python`, but login shells in th container only get python3, th entrypoint's
    # venv never reaches them, nd extraPackages stops at th host unit. ~/.local/bin is on that PATH
    # nd /nix/store is mounted. th d rule is so a fresh box doesnt get a root-owned dir uv cant use
    systemd.tmpfiles.rules =
      let
        home = "${config.services.hermes-agent.stateDir}/home";
        inherit (config.services.hermes-agent) user group;
      in
      [
        "d ${home}/.local 0755 ${user} ${group} -"
        "d ${home}/.local/bin 0755 ${user} ${group} -"
        "L+ ${home}/.local/bin/python - - - - ${pkgs.python3}/bin/python3"
      ];

    services.hermes-agent = {
      enable = true;

      package = inputs.hermes-agent.packages.${pkgs.stdenv.hostPlatform.system}.default.override {
        uv2nix = patchedUv2nix;
      };

      hermesHomeFiles."SOUL.md" = ../../../machines/nixos/iris/SOUL.md;

      environmentFiles = [ config.sops.secrets."hermes/env".path ];
      environment = {
        # hermes only sends OPENAI_API_KEY 2 this exact origin
        OPENAI_BASE_URL = llamaUrl;
        # default-deny, this is ellie nd nobody else
        DISCORD_ALLOWED_USERS = ellie;
        # so luna can @ her in a thread. bots skip DISCORD_ALLOWED_USERS, so this is only ok w th
        # approval patch above + allow_admin_from below. keep her in private servers!!
        DISCORD_ALLOW_BOTS = "mentions";
        # her own fastmail user just 4 broker opt-outs, never ellie's inbox. unbroker only infers
        # hosts for fastmail.com addresses, so a t4t.net one has 2 spell them out
        EMAIL_ADDRESS = "iris@t4t.net";
        EMAIL_SMTP_HOST = "smtp.fastmail.com";
        EMAIL_IMAP_HOST = "imap.fastmail.com";
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
        skills.external_dirs = [ "${irisSkills}" ];
        # th EMAIL_* creds above r also wat auto-starts th email gateway, nd that inbox is full of
        # broker mail. nobody gets 2 talk 2 her thru it
        platforms.email.enabled = false;
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
