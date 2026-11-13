{
  lib,
  fetchFromGitHub,
  buildGoModule,
  gitMinimal,
  versionCheckHook,
}:
# nixpkgs' gh-stack (pkgs/by-name/gh/gh-stack) at 0.1.0, the version the gh-stack agent skill is written against.
buildGoModule (finalAttrs: {
  pname = "gh-stack";
  version = "0.1.0";

  __structuredAttrs = true;

  src = fetchFromGitHub {
    owner = "github";
    repo = "gh-stack";
    tag = "v${finalAttrs.version}";
    hash = "sha256-48JkOeqbvHlCZ2u3LnwJymw55xMQWLTPJLDbV44clGI=";
  };

  vendorHash = "sha256-0Xtr/MOpX4u5GnbRdNxKPA0GpSzi8PIbVc9MmP05De4=";

  # The integration tests drive real git repositories.
  nativeCheckInputs = [ gitMinimal ];
  preCheck = ''
    export HOME=$(mktemp -d)
    git config --global user.name "nix-build"
    git config --global user.email "nix-build@localhost"
  '';

  ldflags = [
    "-s"
    "-w"
    "-X=github.com/github/gh-stack/cmd.Version=${finalAttrs.version}"
  ];

  nativeInstallCheckInputs = [ versionCheckHook ];
  doInstallCheck = true;

  meta = {
    description = "GitHub CLI extension to use stacked PRs";
    homepage = "https://github.github.com/gh-stack/";
    changelog = "https://github.com/github/gh-stack/releases/tag/v${finalAttrs.version}";
    license = lib.licenses.mit;
    mainProgram = "gh-stack";
  };
})
