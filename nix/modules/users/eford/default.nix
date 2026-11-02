# work laptop only, so this is darwin-only
{
  pkgs,
  inputs,
  ...
}:
{
  users.users."eford" = {
    shell = pkgs.fish;
    home = "/Users/eford";
    createHome = true;
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

        # tvsci repos are pushed under my public GH account, so use the noreply email there
        "--scope" = [
          {
            "--when".repositories = [ "~/code/tvsci" ];
            user.email = "15710074+rv32ima@users.noreply.github.com";
          }
          # personal repos are public, so keep the work email out of them
          {
            "--when".repositories = [
              "~/.dotfiles"
              "~/code/infra"
              "~/code/deploy-gate-playground"
              "~/code/zig2nix"
            ];
            user.email = "15710074+rv32ima@users.noreply.github.com";
          }
        ];
      };
    };

    home.sessionVariables = {
      "SERIOUS_MODE_NO_FUNNY_BUSINESS" = "1";
    };

    home.username = "eford";
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
