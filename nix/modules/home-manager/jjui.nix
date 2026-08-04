{ pkgs, config, ... }: {
  home-manager.users."${config.system.primaryUser}" = { config, ... }: {
    home.file.".config/jjui" = {
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/jjui";
      recursive = true;
    };
  };
}
