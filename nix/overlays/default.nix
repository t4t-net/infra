{ inputs, ... }:
final: prev:
let
  inherit (prev) system;
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

  zig = inputs.zig2nix.packages.${system}.zig-0_16_0;

  lib = prev.lib // {
    toBase64 = final.callPackage ../lib/toBase64.nix { };
  };
}
