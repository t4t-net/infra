{
  config,
  lib,
  ...
}:
{
  sops.secrets."users/root/password" = {
    neededForUsers = true;
    sopsFile = ./secrets/password.yaml;
  };

  users.users."root" = {
    home = "/root";
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPUAs4RQBUriBrp7rv2cepCve5eIo6uqFfgs7oPqV9Q" # 1Password -> 'Primary SSH key'
    ];
    openssh.authorizedPrincipals = [
      "ellie"
      "me@ellie.fm"
    ];
    createHome = true;
    hashedPasswordFile = config.sops.secrets."users/root/password".path;
  };
}
