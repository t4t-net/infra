{
  config,
  pkgs,
  ...
}:
{
  home-manager.users."${config.system.primaryUser}" = {
    programs.gh = {
      enable = true;
      # home-manager owns ~/.config/gh/config.yml now!! these r th only non-defaults th hand-written one had
      settings = {
        git_protocol = "https";
        aliases.co = "pr checkout";
      };
      # git creds stay how they r (ssh via url.insteadOf), dont sneak a gh credential helper into git config
      gitCredentialHelper.enable = false;
      extensions = [ pkgs.rv32ima.gh-stack ];
    };
  };
}
