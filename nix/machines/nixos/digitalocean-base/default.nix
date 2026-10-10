{
  inputs,
  lib,
  self,
  ...
}:
{
  imports = [
    (self.lib.nixosModule "nixos/digitalocean-image")

    (self.lib.nixosModule "users/root")
  ];

  config = {
    environment.systemPackages = [
      inputs.disko.packages.x86_64-linux.default
    ];

    systemd.services.sshd.wantedBy = lib.mkForce [ "multi-user.target" ];
    users.users.root.openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPUAs4RQBUriBrp7rv2cepCve5eIo6uqFfgs7oPqV9Q" # 1Password -> 'Primary SSH key'
    ];

    networking.firewall.allowedTCPPorts = [
      22
    ];
  };
}
