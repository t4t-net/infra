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
