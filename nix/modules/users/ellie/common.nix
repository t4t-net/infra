{
  pkgs,
  lib,
  ...
}:
{
  config = {
    users.users."ellie" = {
      openssh.authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPUAs4RQBUriBrp7rv2cepCve5eIo6uqFfgs7oPqV9Q" # 1Password -> 'Primary SSH key'
        "sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29tAAAAIJtlo9dfoKwUfxp4IabM/9IpBHurAVGGAajY6sCzShmBAAAABHNzaDo= eford@eford-20RW02G" # Pinterest Laptop Yubikey
      ];
      shell = pkgs.fish;
      createHome = true;
    };

    # home.stateVersion is per-host state, so it's set by the host (nixos/home-manager.nix
    # defaults it from vars', darwin machines set it themselves), not here
    home-manager.users."ellie" = { config, ... }: {
      home.file.".ssh/t4t-ca".text = ''
        @cert-authority * ${lib.fileContents ../../../../certificates/ssh-host-ca.pub}
      '';

      programs.git = {
        enable = true;
        settings = {
          user = {
            name = "kitty";
            email = "kitty@catmod.ing";
          };
          # t4t-net uses the step ssh cert via the normal agent,, personal repos
          # go thru the github-personal alias in ~/.dotfiles/ssh which uses 1p
          url."git@github-personal:rv32ima/".insteadOf = "git@github.com:rv32ima/";
        };
      };

      programs.jujutsu = {
        settings = {
          user = {
            name = "kitty";
            email = "kitty@catmod.ing";
          };
        };
      };

      # They won't like the praise I get in my terminal,
      # so we should probably turn this off. Just for now.
      home.sessionVariables = {
        "SERIOUS_MODE_NO_FUNNY_BUSINESS" = "1";
      };

      home.username = "ellie";
      home.packages = with pkgs; [
        age
        sops
        typst
        tinymist
        kubectx
        step-cli
        awscli2
        fluxcd
        doctl
      ];
    };
  };
}
