{
  lib,
  config,
  pkgs,
  self,
  ...
}:
{
  options = {
    rv32ima.machine.workstation.enable = lib.mkEnableOption "is this a workstation";
  };

  imports = [
    (self.lib.nixosModule "darwin/aerospace")
    (self.lib.nixosModule "darwin/ssh-askpass-gui")
    (self.lib.nixosModule "home-manager/common")
    (self.lib.nixosModule "home-manager/fish")
    (self.lib.nixosModule "home-manager/ghostty")
    (self.lib.nixosModule "home-manager/neovim")
    (self.lib.nixosModule "home-manager/jujutsu")
    (self.lib.nixosModule "home-manager/claude-code")
    (self.lib.nixosModule "home-manager/jjui")
  ];

  config = {
    environment.shells = [
      pkgs.fish
    ];

    environment.systemPackages = [
      pkgs.openssh
    ];

    programs.zsh.enable = true;

    services.tailscale.enable = true;

    system.defaults.dock.autohide = true;
    system.defaults.dock.mru-spaces = false;
    system.defaults.dock.show-recents = false;
    system.defaults.finder.AppleShowAllExtensions = true;
    system.defaults.finder.AppleShowAllFiles = true;

    system.defaults.NSGlobalDomain.NSAutomaticCapitalizationEnabled = false;
    system.defaults.NSGlobalDomain.NSAutomaticDashSubstitutionEnabled = false;
    system.defaults.NSGlobalDomain.NSAutomaticInlinePredictionEnabled = false;
    system.defaults.NSGlobalDomain.NSAutomaticPeriodSubstitutionEnabled = false;
    system.defaults.NSGlobalDomain.NSAutomaticQuoteSubstitutionEnabled = false;
    system.defaults.NSGlobalDomain.NSAutomaticSpellingCorrectionEnabled = false;
    system.defaults.NSGlobalDomain.NSDocumentSaveNewDocumentsToCloud = false;

    system.defaults.NSGlobalDomain."com.apple.keyboard.fnState" = true;
    system.defaults.WindowManager.AutoHide = true;
  };
}
