{ pkgs, ... }: {
  config = {
    users.users.deploy = {
      group = "deploy";
      openssh.authorizedPrincipals = [
        "ellie"
        "repo:t4t-net/infra:ref:refs/heads/main"
      ];
      shell = pkgs.bashInteractive;
      isSystemUser = true;
    };

    users.groups.deploy = { };

    nix.trustedUsers = [ "@deploy" ];

    security.sudo.extraRules = [
      # Allow execution of any command by all users in group sudo,
      # requiring a password.
      #
      # This sucks, but Colmena doesn't have any hardening yet: see https://github.com/nix-community/colmena/issues/165
      {
        groups = [ "deploy" ];
        commands = [
          {
            command = "ALL";
            options = [ "NOPASSWD" ];
          }
        ];
      }
    ];
  };
}
