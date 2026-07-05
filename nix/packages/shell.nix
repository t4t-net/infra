{
  mkShell,
  tenv,
  step-cli,
  step-kms-plugin,
  openbao,
  colmena,
  ...
}:
mkShell {
  packages = [
    tenv
    step-cli
    step-kms-plugin
    openbao
    colmena
  ];
}
