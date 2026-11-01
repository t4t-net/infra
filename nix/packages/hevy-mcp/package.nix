{
  buildNpmPackage,
  fetchurl,
  jq,
  lib,
}:
buildNpmPackage rec {
  pname = "hevy-mcp";
  version = "6.2.1";

  # th published tarball, cuz dist is already bundled nd building th monorepo means nx + mise + th
  # whole pnpm workspace just 2 get th same files
  src = fetchurl {
    url = "https://registry.npmjs.org/hevy-mcp/-/hevy-mcp-${version}.tgz";
    hash = "sha512-zZpj8lbbxJC+Y4SpAkY5wAkQZFwxdQWXTSKbm6VuNt8LawVH3zN3tdclbOVLTnclc/IDk6IVSKaSxHkXhPoEUA==";
  };

  # upstream has no read-only mode nd a hermes tools.include is client-side, so anyone holding th
  # socket could still call th write tools. this way they just dont exist. bundle filenames r hashed
  # so a version bump fails right here until th patch is redone, which is wat we want
  patches = [ ./read-only.patch ];

  # th lock is generated w/o devDependencies, those r private @hevy-mcp/* workspace pkgs that r
  # bundled into dist already nd arent on npm. full path cuz this runs in th npmDeps fetcher 2, nd
  # that doesnt get our nativeBuildInputs
  postPatch = ''
    ${lib.getExe jq} 'del(.devDependencies, .scripts)' package.json > package.json.new
    mv package.json.new package.json
    cp ${./package-lock.json} package-lock.json
  '';

  npmDepsHash = "sha256-YaDAIaZE3tJQ26QxQd7ntgCFh9SeNLXueWsoUOTJHuo=";
  dontNpmBuild = true;

  meta = {
    description = "Read-only build of the Hevy MCP server";
    homepage = "https://github.com/chrisdoc/hevy-mcp";
    license = lib.licenses.mit;
    mainProgram = "hevy-mcp";
  };
}
