{ pkgs, config, ... }: {
  home-manager.users."${config.system.primaryUser}" = { config, ... }: {
    programs.jujutsu = {
      enable = true;
      # unstable 4 colocated workspaces (jj >= 0.46) so nix nd git just work in em
      package = pkgs.unstable.jujutsu;
    };

    home.file.".config/jj/conf.d" = {
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/jj/conf.d";
      recursive = true;
    };
  };
}
