{
  python3Packages,
}:
# our own cuz th community ones only take a static personal access token, nd those can always write.
# a read-only oauth grant needs something tht refreshes every 2h
python3Packages.buildPythonApplication {
  pname = "ynab-mcp";
  version = "0.1.0";
  format = "other";

  src = ./ynab_mcp.py;
  dontUnpack = true;

  dependencies = with python3Packages; [
    httpx
    mcp
  ];

  installPhase = ''
    runHook preInstall
    install -Dm755 $src $out/bin/ynab-mcp
    runHook postInstall
  '';

  meta.mainProgram = "ynab-mcp";
}
