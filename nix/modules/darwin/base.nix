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

  # eMudhra intermediate CA key compromise, mitigation from
  # https://github.com/NixOS/nixpkgs/issues/576485 -- drop once our nixpkgs pin
  # includes https://github.com/NixOS/nixpkgs/pull/576390 / #576401.
  # (same list as modules/nixos/base.nix)
  security.pki.caCertificateBlacklist = [
    # CVE-2026-111943
    "Comodo AAA Services root"
    # https://hg-edge.mozilla.org/projects/nss/rev/26d38a0c3fb81e7fb2acedbaf4c42dd21dce0517
    "emSign ECC Root CA - G3"
    # https://hg-edge.mozilla.org/projects/nss/rev/8159223c48ceeb1273a1915bca95a517294ab0e0
    "emSign Root CA - C1"
    "emSign ECC Root CA - C3"
  ];

  # Where we are roughly:
  time.timeZone = "America/Los_Angeles";
}
