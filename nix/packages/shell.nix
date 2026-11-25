{
  mkShell,
  tenv,
  step-cli,
  step-kms-plugin,
  openbao,
  colmena,
  zoomies,
  ...
}:
mkShell {
  packages = [
    tenv
    step-cli
    step-kms-plugin
    openbao
    colmena
    # 4 `zoomies status`
    zoomies
  ];
}
