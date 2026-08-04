{
  pkgs,
  lib,
  dotnet-runtime_10,
  glibc,
  makeWrapper,
  ...
}:
let
  name = "vintagestory";
  version = "1.22.6";
  dotnet = dotnet-runtime_10;
in
pkgs.stdenv.mkDerivation {
  inherit name version;

  src = pkgs.fetchurl {
    url = "https://cdn.vintagestory.at/gamefiles/stable/vs_server_linux-x64_${version}.tar.gz";
    hash = "sha256-r8jr3JKSvBSZZIKUaGM7vaYh+0hhIt9A06FEJT90ook=";
  };

  nativeBuildInputs = [
    makeWrapper
  ];

  phases = [
    "installPhase"
    "fixupPhase"
  ];

  installPhase = ''
    # Crude hack I stole from https://git.bellsworne.tech/chrisbell/vssm/src/branch/master/downloader.go. 
    # I think the correct thing is to just get it from glibc, but oh well.
    DOTNET_INTERPRETER=$(patchelf --print-interpreter "${dotnet}/bin/dotnet")
    mkdir -p $out
    tar -C $out -xvf $src
    patchelf --set-interpreter $DOTNET_INTERPRETER $out/VintagestoryServer
    patchelf --add-rpath "${glibc}/lib" $out/VintagestoryServer
    patchelf --add-rpath "${pkgs.stdenv.cc.cc.lib}/lib" $out/VintagestoryServer
    mv $out/VintagestoryServer $out/.VintagestoryServer
    makeWrapper $out/.VintagestoryServer $out/VintagestoryServer \
      --set DOTNET_ROOT "${dotnet}/share/dotnet"
  '';
}
