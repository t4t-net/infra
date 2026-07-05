{
  pkgs,
  config,
  inputs,
  self,
  ...
}:
{
  home-manager.users."${config.system.primaryUser}" = { config, ... }: {
    programs = {
      home-manager.enable = true;
      zsh.enable = true;

      starship = {
        enable = true;
        # TODO: don't do this anymore
        settings = builtins.fromTOML (builtins.readFile "${inputs.dotfiles}/starship/starship.toml");
      };

      direnv = {
        enable = true;
        enableFishIntegration = true;
        nix-direnv.enable = true;
      };

      tmux = {
        enable = true;
        baseIndex = 1;
        newSession = true;
        shell = "${pkgs.fish}/bin/fish";
        historyLimit = 100000;
        plugins = with pkgs; [
          tmuxPlugins.better-mouse-mode
        ];
      };
    };

    rv32ima.services.ssh-agent.enable = true;

    home.file.".ssh/config" = {
      enable = true;
      recursive = true;
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/ssh/${config.home.username}.config";
    };

    home.file."bin" = {
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/bin";
      recursive = true;
    };

    home.sessionPath = [
      "${config.home.homeDirectory}/bin"
    ];

    home.packages = with pkgs; [
      # Programming Languages
      nodejs_latest
      go_latest
      # (rust-bin.stable.latest.default.override {
      #   extensions = [ "rust-src" ];
      # })

      claude-code
      git
      eza
      bat
      gnupg
      diffedit3
      sccache
      nixfmt
      packer
      buf
      graphviz
      bazelisk
      jujutsu
      cargo-mommy
      tenv
      nix-your-shell
      gh
      python313
      prek
      keep-sorted
      nix-search
      nix-index
    ];

    home.file.".config/1Password/ssh/agent.toml" = {
      enable = true;
      recursive = true;
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/1Password/ssh/agent.${config.home.username}.toml";
    };
  };
}
