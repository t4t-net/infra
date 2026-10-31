# Set of sanity-keeping configurations.
# All machines should import this module.

{
  self,
  pkgs,
  inputs,
  config,
  ...
}:

{
  imports = [
    inputs.sops-nix.darwinModules.sops
    (self.lib.nixosModule "shared/nix-config")
    (self.lib.nixosModule "shared/nixpkgs")
    (self.lib.nixosModule "darwin/home-manager")
    (self.lib.nixosModule "darwin/nix-homebrew")
  ];

  nix.settings.trusted-users = [
    "${config.system.primaryUser}"
  ];

  # Useful tools.
  environment.systemPackages = with pkgs; [
    htop
    jq
    vim
    wget
    # persistent terminal sessions for ssh
    tmux
  ];

  nix.settings.substituters = [
    "https://cache.t4t.net"
  ];

  nix.settings.trusted-public-keys = [
    "cache.t4t.net-1:7NimrD/skv9tL7c3UjgwMxpup/RNcvzd7yrH0QNnlF0="
  ];

  nixpkgs.overlays = builtins.attrValues self.overlays;

  security.pki.caCertificateBlacklist = [
    # CVE-2026-111943
    "Comodo AAA Services root"
  ];

  # Where we are roughly:
  time.timeZone = "America/Los_Angeles";
}
