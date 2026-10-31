{ inputs, ... }:
final: prev:
let
  inherit (prev.stdenv.hostPlatform) system;
  packagesDir = prev.lib.makeScope prev.newScope (
    self:
    (prev.lib.packagesFromDirectoryRecursive {
      inherit (self) callPackage;
      directory = ../packages;
    })
  );
in
{
  rv32ima = prev.lib.filterAttrs (
    n: v: if prev.system != "x86_64-linux" && n == "mlx-kernel" then false else true
  ) packagesDir;

  # one shared nixpkgs-unstable instance per pkgs, instead of every module importing its own
  unstable = import inputs.nixpkgs-unstable {
    inherit system;
    config.allowUnfree = true;
  };

  zig = inputs.zig2nix.packages.${system}.zig-0_16_0;

  lib = prev.lib // {
    toBase64 = final.callPackage ../lib/toBase64.nix { };
  };
}
