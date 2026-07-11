{
  python3Packages,
  fetchFromGitHub,
  makeWrapper,
  fetchPypi,
  lib,
  ...
}:
let
  name = "soularr";
  version = "1.2.2";

  slskd-api = python3Packages.buildPythonPackage {
    pname = "slskd-api";
    version = "0.1.5"; # check pypi 4 latest
    format = "setuptools"; # or "pyproject" if it has

    src = fetchPypi {
      pname = "slskd-api";
      version = "0.1.5";
      hash = "sha256-LmWP7bnK5IVid255qS2NGOmyKzGpUl3xsO5vi5uJI88=";
    };

    propagatedBuildInputs = with python3Packages; [
      pip
      setuptools
      setuptools-git-versioning
      requests
    ];
  };
in
python3Packages.buildPythonApplication {
  pname = name;
  inherit version;
  format = "other";

  nativeBuildInputs = [ makeWrapper ];

  propagatedBuildInputs = with python3Packages; [
    pyarr
    music-tag
    slskd-api
    flask
    waitress
  ];

  src = fetchFromGitHub {
    owner = "mrusse";
    repo = "soularr";
    rev = "f9e0ab922fd928a6d5d39cc9ddc0b0734006ddac";
    hash = "sha256-gtz99+DiFjJZuq54qo5C+5Exx++S+ePzldgDM9NHAOA=";
  };

  installPhase = ''
    mkdir -p $out/bin $out/lib/soularr
    cp *.py $out/lib/soularr/
    cp -r webui $out/lib/soularr/
    makeWrapper ${python3Packages.python.interpreter} $out/bin/soularr \
      --set PYTHONPATH "$PYTHONPATH" \
      --add-flags "$out/lib/soularr/soularr.py"

    makeWrapper ${python3Packages.python.interpreter} $out/bin/soularr-webui \
      --set PYTHONPATH "$PYTHONPATH" \
      --add-flags "$out/lib/soularr/webui/webui.py"
  '';

}
