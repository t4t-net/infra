{ config, inputs, ... }:
{
  imports = [
    inputs.nix-homebrew.darwinModules.nix-homebrew
  ];

  config = {
    nix-homebrew = {
      autoMigrate = true;
      enable = true;
      enableRosetta = true;
      user = config.system.primaryUser;
      taps = {
        "homebrew/homebrew-core" = inputs.homebrew-core;
        "homebrew/homebrew-cask" = inputs.homebrew-cask;
        "homebrew/homebrew-bundle" = inputs.homebrew-bundle;
        "theseal/homebrew-ssh-askpass" = inputs.darwin-ssh-askpass;
      };
      mutableTaps = false;
      # brew >= 6 refuses 2 load formulae from non-official taps unless trusted
      trust.formulae = [
        "theseal/ssh-askpass/ssh-askpass"
      ];
    };

    homebrew = {
      enable = true;
      global.autoUpdate = false;
      casks = [
        "1password-cli"
        "setapp"
        "orbstack"
        "jordanbaird-ice"
      ];
    };
  };
}
