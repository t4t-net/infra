{
  lib,
  python3Packages,
  openssl,
}:
# luna's github identity!! mints luna-t4t app tokens from th 1p key 4 git (credential helper)
# nd gh. stdlib python, openssl does th RS256. op + gh come from PATH on purpose, so its th op
# tht talks 2 ellie's 1p desktop app. per-repo setup (in a repo luna pushes from):
#   jj git remote add luna https://github.com/t4t-net/infra.git
#   git config credential.https://github.com.helper ''        # drop th osxkeychain fallback
#   git config --add credential.https://github.com.helper '!luna-gh credential'
python3Packages.buildPythonApplication {
  pname = "luna-gh";
  version = "0.1.0";
  format = "other";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.fileFilter (f: f.hasExt "py") ./.;
  };

  nativeCheckInputs = [ openssl ];
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    LUNA_GH_OPENSSL=${lib.getExe openssl} ${python3Packages.python.interpreter} -m unittest discover -s tests -v
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 luna_gh.py $out/bin/luna-gh
    runHook postInstall
  '';

  makeWrapperArgs = [
    "--set-default"
    "LUNA_GH_OPENSSL"
    (lib.getExe openssl)
  ];

  meta.mainProgram = "luna-gh";
}
