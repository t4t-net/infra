{
  lib,
  python3Packages,
  makeWrapper,
  nix-eval-jobs,
  git,
}:
# a tiny ci 2 replace hydra: poll main, nix-eval-jobs, build, nix copy 2 th cache, publish
# latest/<job>.json as static files. see DESIGN.md 4 th contract. stdlib only
python3Packages.buildPythonApplication {
  pname = "zoomies";
  version = "0.1.0";
  format = "other";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.fileFilter (f: f.hasExt "py") ./.;
  };

  nativeBuildInputs = [ makeWrapper ];

  # whole ticks against a fake nix, so no daemon or network in th sandbox
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    ${python3Packages.python.interpreter} -m unittest discover -s tests -v
    runHook postCheck
  '';

  # we wrap it ourselves below, no need 4 a 2nd wrapper on top
  dontWrapPythonPrograms = true;

  # th cli imports its sibling modules from its own dir. nix itself is NOT on th path on purpose:
  # th system nix matches th daemon nd has th machines/substituters config
  installPhase = ''
    runHook preInstall
    install -Dm755 zoomies.py $out/libexec/zoomies/zoomies.py
    for f in *.py; do
      [ "$f" = zoomies.py ] || install -Dm644 "$f" -t $out/libexec/zoomies/
    done
    makeWrapper $out/libexec/zoomies/zoomies.py $out/bin/zoomies \
      --prefix PATH : ${
        lib.makeBinPath [
          nix-eval-jobs
          git
        ]
      }
    runHook postInstall
  '';

  meta.mainProgram = "zoomies";
}
