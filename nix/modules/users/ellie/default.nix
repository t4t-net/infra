{
  pkgs,
  options,
  config,
  inputs,
  self,
  lib,
  ...
}:
let
  homeDirectory =
    user:
    if (lib.hasSuffix "darwin" config.nixpkgs.hostPlatform.config) then
      "/Users/${user}"
    else
      "/home/${user}";

  canSetPassword = builtins.hasAttr "hashedPasswordFile" (options.users.users.type.getSubOptions { });
in
{
  config = {
    sops.secrets."users/ellie/password" = lib.mkIf canSetPassword {
      neededForUsers = true;
      sopsFile = ./secrets/password.yaml;
    };

    users.users."ellie" = {
      openssh.authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPUAs4RQBUriBrp7rv2cepCve5eIo6uqFfgs7oPqV9Q" # 1Password -> 'Primary SSH key'
        "sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29tAAAAIJtlo9dfoKwUfxp4IabM/9IpBHurAVGGAajY6sCzShmBAAAABHNzaDo= eford@eford-20RW02G" # Pinterest Laptop Yubikey
      ];
      shell = pkgs.fish;
      home = homeDirectory "ellie";
      createHome = true;
    }
    //
      lib.optionalAttrs
        (builtins.hasAttr "openssh.authorizedPrincipals" (options.users.users.type.getSubOptions { }))
        {
          openssh.authorizedPrincipals = [
            "ellie"
          ];
        }
    // lib.optionalAttrs (builtins.hasAttr "extraGroups" (options.users.users.type.getSubOptions { })) {
      extraGroups = [
        "wheel"
        "trusted"
      ];
    }
    //
      lib.optionalAttrs (builtins.hasAttr "isNormalUser" (options.users.users.type.getSubOptions { }))
        {
          isNormalUser = true;
        }
    // lib.optionalAttrs canSetPassword {
      hashedPasswordFile = config.sops.secrets."users/ellie/password".path;
    };

    home-manager.users."ellie" = { config, ... }: {
      home.file.".ssh/t4t-ca".text = ''
        @cert-authority * ${lib.fileContents ../../../../certificates/ssh-host-ca.pub}
      '';

      programs.git = {
        enable = true;
        settings = {
          user = {
            name = "Ellie Ford";
            email = "me@ellie.fm";
          };
        };
      };

      programs.jujutsu = {
        settings = {
          user = {
            name = "Ellie Ford";
            email = "me@ellie.fm";
          };
        };
      };

      # They won't like the praise I get in my terminal,
      # so we should probably turn this off. Just for now.
      home.sessionVariables = {
        "SERIOUS_MODE_NO_FUNNY_BUSINESS" = "1";
      };

      home.username = "ellie";
      home.stateVersion = "26.05";
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
