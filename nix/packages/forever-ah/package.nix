{
  python3Packages,
}:
# wow forever AH price history straight from th battle.net api, stdlib only
python3Packages.buildPythonApplication {
  pname = "forever-ah";
  version = "0.1.0";
  format = "other";

  src = ./forever_ah.py;
  dontUnpack = true;

  installPhase = ''
    runHook preInstall
    install -Dm755 $src $out/bin/forever-ah
    runHook postInstall
  '';

  meta.mainProgram = "forever-ah";
}
