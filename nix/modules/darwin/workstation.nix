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
    (self.lib.nixosModule "home-manager/gh")
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

    home-manager.users.${config.system.primaryUser}.rv32ima.services.ssh-agent.enable = true;

    # launchd-started apps (Rex.app's ssh://) get apple's empty launchd agent, not fish's
    # SSH_AUTH_SOCK, so point ssh at our agent's fixed link. same rule as th shell init in
    # home-manager/ssh-agent.nix: hands off inside ai-sandbox, which brings its own agent.
    # cant test SSH_AUTH_SOCK itself here: ssh runs Match exec thru $SHELL -c nd fish/zsh init
    # re-export it b4 th test runs. /bin/sh cuz $SHELL may b fish
    programs.ssh.extraConfig = ''
      Match exec "/bin/sh -c 'test x$AI_SANDBOX_ACTIVE = x'"
        IdentityAgent ~/.ssh/agent.sock
    '';

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
