{
  config,
  pkgs,
  lib,
  ...
}:
{
  # on darwin ghostty comes from th cask, not th store!! once macos launches an
  # .app it slaps com.apple.macl on th bundle nd then nix gc cant delete it
  # (not even as root) so every old ghostty-bin wud wedge th nightly gc >,<
  homebrew.casks = lib.mkIf pkgs.stdenv.isDarwin [ "ghostty" ];

  home-manager.users."${config.system.primaryUser}" = { config, ... }: {
    programs.ghostty = {
      enable = true;
      # shell integration still works, it just reads $GHOSTTY_RESOURCES_DIR from th app
      package = lib.mkIf pkgs.stdenv.isDarwin null;
    };

    home.file.".config/ghostty" = {
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/ghostty";
      recursive = true;
    };
  };
}
