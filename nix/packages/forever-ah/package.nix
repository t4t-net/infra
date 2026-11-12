{
  lib,
  python3Packages,
}:
# wow forever AH price history straight from th battle.net api, plus client db2 tables off
# blizzard's CDN (tact.py) nd QuestieDB's quest data (questie.py). stdlib only
python3Packages.buildPythonApplication {
  pname = "forever-ah";
  version = "0.1.0";
  format = "other";

  src = lib.fileset.toSource {
    root = ./.;
    # every module (nd th tests' .py), but not __pycache__ or th addon's lua
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (f: f.hasExt "py") ./.)
      ./tests/fixture.sqlite.gz
      ./tests/golden
    ];
  };

  # export on a frozen fixture vs tests/golden, so a refactor tht moves a number fails th build.
  # offline: th test turns any api call into a failure
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    ${python3Packages.python.interpreter} -m unittest discover -s tests -v
    runHook postCheck
  '';

  # th cli imports its sibling modules from its own dir, nd python resolves th bin symlink 2 find it
  installPhase = ''
    runHook preInstall
    install -Dm755 forever_ah.py $out/libexec/forever-ah/forever_ah.py
    for f in *.py; do
      [ "$f" = forever_ah.py ] || install -Dm644 "$f" -t $out/libexec/forever-ah/
    done
    mkdir -p $out/bin
    ln -s $out/libexec/forever-ah/forever_ah.py $out/bin/forever-ah
    runHook postInstall
  '';

  meta.mainProgram = "forever-ah";
}
