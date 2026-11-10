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
    fileset = lib.fileset.unions [
      ./forever_ah.py
      ./questie.py
      ./tact.py
    ];
  };

  # th cli imports tact from its own dir, nd python resolves th bin symlink 2 find it
  installPhase = ''
    runHook preInstall
    install -Dm755 forever_ah.py $out/libexec/forever-ah/forever_ah.py
    install -Dm644 tact.py questie.py -t $out/libexec/forever-ah/
    mkdir -p $out/bin
    ln -s $out/libexec/forever-ah/forever_ah.py $out/bin/forever-ah
    runHook postInstall
  '';

  meta.mainProgram = "forever-ah";
}
