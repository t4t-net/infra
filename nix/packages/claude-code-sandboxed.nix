{
  claude-code,
  makeBinaryWrapper,
  symlinkJoin,
  writeShellScript,
}:
let
  # Claude Code self-spawns (agent view supervisor, its sessions, teammate
  # panes, update relaunches) exec the raw binary directly, never `claude` on
  # PATH, so ~/bin/claude can't put them in ai-sandbox. The process wrapper
  # can: https://code.claude.com/docs/en/corporate-launcher
  # ai-sandbox refuses to nest, so spawns from an already-sandboxed process
  # pass straight through (they inherit its Seatbelt profile).
  sandboxLauncher = writeShellScript "claude-sandbox-launcher" ''
    if [[ "''${AI_SANDBOX_ACTIVE:-}" == "1" || ! -x /usr/local/bin/ai-sandbox ]]; then
      exec "$@"
    fi
    export AI_SANDBOX_QUIET=1
    exec /usr/local/bin/ai-sandbox "$@"
  '';
in
symlinkJoin {
  name = "claude-code-sandboxed-${claude-code.version}";
  paths = [ claude-code ];
  nativeBuildInputs = [ makeBinaryWrapper ];
  postBuild = ''
    rm $out/bin/claude
    makeWrapper ${claude-code}/bin/claude $out/bin/claude \
      --set CLAUDE_CODE_PROCESS_WRAPPER ${sandboxLauncher}
  '';
  inherit (claude-code) meta;
}
