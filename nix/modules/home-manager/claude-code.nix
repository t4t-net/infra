{
  pkgs,
  config,
  inputs,
  ...
}:
{
  home-manager.users."${config.system.primaryUser}" =
    { config, lib, ... }:
    let
      voiceHooks = pkgs.rv32ima.luna-voice-hooks;
      # th hook events this module owns in ~/.claude/settings.json!! other events nd keys r left alone
      managedHooks = {
        UserPromptSubmit = [
          {
            hooks = [
              {
                type = "command";
                command = "${voiceHooks}/bin/luna-voice-reminder";
                timeout = 5;
              }
            ];
          }
        ];
        Stop = [
          {
            hooks = [
              {
                type = "command";
                command = "${voiceHooks}/bin/luna-voice-lint";
                # async: th lint lands w ellie's next prompt instead of making me resend a message she already has
                async = true;
              }
            ];
          }
        ];
      };
    in
    {
      home.packages = [
        (pkgs.rv32ima.claude-code-sandboxed.override { inherit (pkgs.unstable) claude-code; })
        # luna's own github identity (th luna-t4t app), so her PRs need ellie's approval
        pkgs.rv32ima.luna-gh
        # claude code on halogen (svc:llm on experimental-skin) instead of anthropic. th key is ellie's own
        # (ellie-api-key in experimental-skin's sops), so halogen gives it a prompt cache separate from iris's
        (pkgs.writeShellApplication {
          name = "claude-halogen";
          text = ''
            key_file="''${XDG_CONFIG_HOME:-$HOME/.config}/halogen/api-key"
            if [[ ! -r "$key_file" ]]; then
              echo "claude-halogen: no key at $key_file (ellie-api-key in experimental-skin's llama-cpp.yaml)" >&2
              exit 1
            fi
            unset ANTHROPIC_API_KEY
            export ANTHROPIC_BASE_URL=https://llm.tail09d5b.ts.net
            ANTHROPIC_AUTH_TOKEN=$(<"$key_file")
            export ANTHROPIC_AUTH_TOKEN
            # claude code asks 4 its model's whole output limit, over halogen's 65536 cap
            export CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000
            # halogen answers any name. a non-claude one makes claude code assume a 200k window (measured)
            # instead of opus's 1M, nd halogen caps a request at 262144
            model=qwen3.8-flash-next
            export ANTHROPIC_MODEL=$model
            export ANTHROPIC_DEFAULT_OPUS_MODEL=$model
            export ANTHROPIC_DEFAULT_SONNET_MODEL=$model
            export ANTHROPIC_DEFAULT_HAIKU_MODEL=$model
            exec claude "$@"
          '';
        })
      ];

      home.file.".claude" = {
        enable = true;
        recursive = true;
        source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/claude";
      };

      # settings.json is gitignored runtime state (claude code rewrites it 4 /model, /effort etc), so th hooks
      # get merged in on every switch instead of living in it. a `--settings` flag on th wrapper wud miss th
      # sessions claude code spawns itself, cuz those exec th raw binary
      home.activation.claudeVoiceHooks = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
        settings="${config.home.homeDirectory}/.claude/settings.json"
        current=$(cat "$settings" 2>/dev/null || echo '{}')
        merged=$(${pkgs.jq}/bin/jq --argjson managed ${lib.escapeShellArg (builtins.toJSON managedHooks)} \
          '.hooks = ((.hooks // {}) + $managed)' <<<"$current")
        run ${pkgs.bash}/bin/bash -c 'printf "%s\n" "$1" > "$2"' _ "$merged" "$settings"
      '';
    };
}
