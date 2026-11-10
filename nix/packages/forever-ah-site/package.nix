{
  buildNpmPackage,
  lib,
}:
# th forever gold meta page, built on t4t.net's ascii components. data.json isnt in here,
# forever-ah export writes it next 2 a copy of this every hour
buildNpmPackage {
  pname = "forever-ah-site";
  version = "0.1.0";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.difference ./. ./package.nix;
  };

  npmDepsHash = "sha256-gmhaGMnTQ7DjirzW4cZYd00SbUxl3QtgvWsnjBc8wj8=";

  installPhase = ''
    runHook preInstall
    cp -r dist $out
    runHook postInstall
  '';
}
