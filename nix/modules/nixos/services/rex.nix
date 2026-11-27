{
  inputs,
  config,
  lib,
  ...
}:
# rex personal server 4 ellie,, a systemd user service so terminals run as her. th rex nixos
# module's shared server runs everything as th `rex` account, nd its login server (root +
# accounts mapping) is overkill 4 one person. reach it over ssh w `rex -S ssh://<host>`
let
  rexPackage = config.home-manager.users.ellie.programs.rex.package;
in
{
  config = {
    home-manager.users.ellie = {
      imports = [ inputs.rex.homeManagerModules.default ];

      services.rex.enable = true;
      # home-manager/common.nix owns ~/.ssh/config (out-of-store symlink 2 dotfiles), so hm's
      # programs.ssh cant, nd th xterm-rex fallback goes in /etc/ssh/ssh_config below instead
      programs.rex.sshGuard = false;
    };

    # without lingering th user service stops at logout nd takes every session w it
    users.users.ellie.linger = true;

    # same Include th rex nixos module adds: ssh from a rex terminal 2 a host w/o th xterm-rex
    # terminfo sends xterm-256color instead
    programs.ssh.extraConfig = lib.mkAfter ''
      Include ${rexPackage}/share/rex/ssh_config.d/50-rex.conf
    '';
  };
}
