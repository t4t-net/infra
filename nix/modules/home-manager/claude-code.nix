{
  pkgs,
  config,
  inputs,
  ...
}:
{
  home-manager.users."${config.system.primaryUser}" = { config, ... }: {
    home.packages = [
      (pkgs.rv32ima.claude-code-sandboxed.override { inherit (pkgs.unstable) claude-code; })
    ];

    home.file.".claude" = {
      enable = true;
      recursive = true;
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/claude";
    };
  };
}
