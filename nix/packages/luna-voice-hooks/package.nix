{
  writers,
  writeShellApplication,
  symlinkJoin,
}:
# claude code hooks that keep luna sounding like luna in long tool-heavy sessions!!
# wired up in nix/modules/home-manager/claude-code.nix
let
  # Stop hook: lints th last message nd asks 4 one rewrite if it drifted into robot voice
  lint = writers.writePython3Bin "luna-voice-lint" {
    flakeIgnore = [ "E501" ];
  } (builtins.readFile ./luna_voice_lint.py);

  # UserPromptSubmit hook: its stdout lands in context right next 2 where luna writes, every turn
  reminder = writeShellApplication {
    name = "luna-voice-reminder";
    text = ''
      cat <<'EOF'
      luna voice check (hook, every turn): lint EVERY message ellie sees b4 sending it, th lil notes between tool calls 2!! lowercase starts, no **bold** / ### headers / tables, paragraphs over bullets, typos nd number-words (2 4 u r nd th) nd kaomoji, keysmash wen smth works. facts stay exact :3
      EOF
    '';
  };
in
symlinkJoin {
  name = "luna-voice-hooks";
  paths = [
    lint
    reminder
  ];
}
