{ inputs, self, ... }:
{
  imports = [
    inputs.home-manager.nixosModules.home-manager
    (self.lib.nixosModule "home-manager/common")
    (self.lib.nixosModule "home-manager/fish")
    (self.lib.nixosModule "home-manager/neovim")
    (self.lib.nixosModule "home-manager/jujutsu")
  ];

  config = {
    home-manager.useGlobalPkgs = true;
    home-manager.useUserPackages = true;
    home-manager.extraSpecialArgs = {
      inherit inputs;
    };
    home-manager.sharedModules = [
      # th hm manpage evals every hm option 2 render docs, per user, on every host eval
      { manual.manpages.enable = false; }
    ];
  };
}
