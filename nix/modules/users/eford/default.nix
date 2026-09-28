{
  pkgs,
  options,
  config,
  lib,
  inputs,
  self,
  ...
}:
let
  homeDirectory =
    user:
    if (lib.hasSuffix "darwin" config.nixpkgs.hostPlatform.config) then
      "/Users/${user}"
    else
      "/home/${user}";

in
{
  users.users."eford" = {
    shell = pkgs.fish;
    home = homeDirectory "eford";
    createHome = true;
  }
  // lib.optionalAttrs (builtins.hasAttr "extraGroups" (options.users.users.type.getSubOptions { })) {
    extraGroups = [
      "wheel"
      "trusted"
    ];
  }
  //
    lib.optionalAttrs (builtins.hasAttr "isNormalUser" (options.users.users.type.getSubOptions { }))
      {
        isNormalUser = true;
      };

  home-manager.users."eford" = {
    programs.git = {
      enable = true;
      settings = {
        user = {
          email = "eford@pinterest.com";
          name = "Ellie Ford";
        };

        "url \"ssh://git@github.com/\"" = {
          insteadOf = "https://github.com/";
        };
      };
    };

    programs.jujutsu = {
      settings = {
        user = {
          name = "Ellie Ford";
          email = "eford@pinterest.com";
        };
      };
    };

    home.sessionVariables = {
      "SERIOUS_MODE_NO_FUNNY_BUSINESS" = "1";
    };

    home.username = "eford";
    home.stateVersion = "25.11";
    home.packages = with pkgs; [
      zig
      inputs.zls.packages.${system}.default

      duckdb
      google-cloud-sdk
      awscli2
      rclone
    ];
  };

}
