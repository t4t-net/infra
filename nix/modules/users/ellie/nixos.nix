{ config, ... }:
{
  config = {
    sops.secrets."users/ellie/password" = {
      neededForUsers = true;
      sopsFile = ./secrets/password.yaml;
    };

    # home defaults to /home/ellie via isNormalUser
    users.users."ellie" = {
      isNormalUser = true;
      extraGroups = [
        "wheel"
        "trusted"
      ];
      openssh.authorizedPrincipals = [
        "ellie"
        "me@ellie.fm"
      ];
      hashedPasswordFile = config.sops.secrets."users/ellie/password".path;
    };
  };
}
