{ platform, ... }:
{
  imports = [
    ./common.nix
    ./${platform}.nix
  ];
}
