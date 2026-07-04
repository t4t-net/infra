{
  description = "ellie's nix flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-darwin.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";
    flake-utils.url = "github:numtide/flake-utils";
    flake-parts.url = "github:hercules-ci/flake-parts";
    nix-darwin = {
      url = "github:nix-darwin/nix-darwin/nix-darwin-26.05";
      inputs.nixpkgs.follows = "nixpkgs-darwin";
    };
    nix-homebrew = {
      url = "github:zhaofengli-wip/nix-homebrew";
    };
    homebrew-core = {
      url = "github:homebrew/homebrew-core";
      flake = false;
    };
    homebrew-cask = {
      url = "github:homebrew/homebrew-cask";
      flake = false;
    };
    homebrew-bundle = {
      url = "github:homebrew/homebrew-bundle";
      flake = false;
    };
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    zig = {
      url = "github:mitchellh/zig-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    zls = {
      url = "github:zigtools/zls/0.15.0";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.zig-overlay.follows = "zig";
    };
    vscode-server = {
      url = "github:nix-community/nixos-vscode-server";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    disko = {
      url = "github:nix-community/disko";
    };
    nixos-wsl = {
      url = "github:nix-community/NixOS-WSL/main";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    microvm = {
      url = "github:microvm-nix/microvm.nix";
      inputs.flake-utils.follows = "flake-utils";
    };
    colmena.url = "github:zhaofengli/colmena";
    darwin-ssh-askpass = {
      url = "github:theseal/homebrew-ssh-askpass";
      flake = false;
    };
    lanzaboote.url = "github:rv32ima/lanzaboote";
    lanzaboote.inputs.nixpkgs.follows = "nixpkgs";
    copyparty.url = "github:9001/copyparty";
    copyparty.inputs.nixpkgs.follows = "nixpkgs";
    comin.url = "github:nlewo/comin";
    comin.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    inputs@{
      self,
      nixpkgs,
      flake-parts,
      nix-darwin,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } (
      { inputs, ... }:
      {
        systems = [
          "x86_64-linux"
          "aarch64-darwin"
        ];

        flake =
          let
            inherit (inputs) colmena;
            lib = nixpkgs.lib;

            getMachineFiles =
              type:
              builtins.attrNames (lib.filterAttrs (_: v: v == "directory") (builtins.readDir ./machines/${type}));

            nixosMachineFiles = getMachineFiles "nixos";
            darwinMachineFiles = getMachineFiles "darwin";
          in
          {
            darwinConfigurations = builtins.listToAttrs (
              map (hostName: {
                name = hostName;
                value = self.lib.darwinSystem' hostName ./machines/darwin/${hostName}/default.nix;
              }) darwinMachineFiles
            );

            nixosConfigurations = builtins.listToAttrs (
              builtins.concatLists (
                map (
                  hostName:
                  (
                    if builtins.pathExists ./machines/nixos/${hostName}/default.nix then
                      [
                        {
                          name = hostName;
                          value = self.lib.nixosSystem' hostName ./machines/nixos/${hostName}/default.nix;
                        }
                      ]
                    else
                      [ ]
                  )
                  ++ (
                    if builtins.pathExists ./machines/nixos/${hostName}/installer.nix then
                      [
                        {
                          name = "${hostName}-installer";
                          value = self.lib.nixosSystem' hostName ./machines/nixos/${hostName}/installer.nix;

                        }

                      ]
                    else
                      [ ]
                  )
                ) nixosMachineFiles
              )
            );

            ciBuilders =
              let
                mkNixBuilders = import ./lib/mkNixMachines.nix { inherit lib; };
              in
              mkNixBuilders (map (m: m // { sshKey = null; }) [
                (self.lib.machineAsBuilder "unmusique")
                (self.lib.machineAsBuilder "peer2peer")
                (self.lib.machineAsBuilder "psychoboost")
                (self.lib.machineAsBuilder "fadeoutz")
              ]);

            colmenaHive = colmena.lib.makeHive self.outputs.colmena;

            colmena =
              let
                blacklistedNodes = [
                  "nixos-netboot"
                  "ca-node"
                ];
                conf = lib.attrsets.filterAttrs (
                  name: _:
                  (lib.strings.hasSuffix "-installer" name) == false && (builtins.elem name blacklistedNodes) == false
                ) inputs.self.nixosConfigurations;
              in
              {
                meta = {
                  nixpkgs = import nixpkgs {
                    system = "x86_64-linux";
                  };
                  nodeSpecialArgs = builtins.mapAttrs (_: value: value._module.specialArgs) conf;
                  nodeNixpkgs = builtins.mapAttrs (_: value: value.pkgs) conf;
                };
              }
              // (builtins.mapAttrs (name: value: {
                imports = value._module.args.modules;
                deployment = self.lib.vars.machines.${name}.deployment or { };
              }) conf);

            hydraJobs = {
              legacyPackages.x86_64-linux = self.legacyPackages.x86_64-linux;
              packages.x86_64-linux =
                let
                  pkgs = import inputs.nixpkgs {
                    system = "x86_64-linux";
                    overlays = builtins.attrValues inputs.self.overlays;
                  };
                in
                {
                  inherit (pkgs) colmena;
                };
              nixos =
                let
                  mkClosure = machine: self.nixosConfigurations.${machine}.config.system.build.toplevel;
                  mkNetboot = machine: self.nixosConfigurations.${machine}.config.system.build.netboot;
                  machineAndInstaller = machine: {
                    "${machine}" = mkClosure machine;
                    "${machine}-installer" = mkNetboot "${machine}-installer";
                  };
                in
                lib.mergeAttrsList [
                  (machineAndInstaller "peer2peer")
                  (machineAndInstaller "ghostholding")
                  (machineAndInstaller "pawpatch")
                  (machineAndInstaller "psychoboost")
                  (machineAndInstaller "unmusique")
                  (machineAndInstaller "fadeoutz")
                ];
            };

            lib = {
              vars = {
                machines = import ./vars/machines.nix inputs;
              };

              machineAsBuilder =
                machineName:
                let
                  vars' = self.lib.vars.machines.${machineName};
                  toBase64 = import ./lib/toBase64.nix { inherit lib; };
                in
                if vars' ? build then
                  {
                    inherit (vars'.build)
                      maxJobs
                      sshUser
                      supportedFeatures
                      speedFactor
                      ;
                    inherit (vars') system;
                    hostName = machineName;
                    publicHostKey = toBase64 vars'.sshPublicKey;
                    sshKey = "/etc/nix/builder_ed25519";
                    protocol = "ssh";
                    mandatoryFeatures = [ ];
                  }
                else
                  lib.assertMsg false "machineAsBuilder must be called on a machine that has a build section";

              nixosSystem =
                machineName: self.lib.nixosSystem' machineName ./machines/nixos/${machineName}/configuration.nix;

              nixosSystem' =
                machineName: machineModule:
                nixpkgs.lib.nixosSystem {
                  modules = [
                    { networking.hostName = machineName; }
                    (self.lib.nixosModule "nixos/base")
                    machineModule
                  ];
                  specialArgs = {
                    inherit self inputs;
                    vars = self.lib.vars;
                    vars' = self.lib.vars.machines.${machineName} or { };
                  };
                };

              darwinSystem =
                machineName: self.lib.darwinSystem' machineName ./machines/${machineName}/configuration.nix;

              darwinSystem' =
                machineName: machineModule:
                nix-darwin.lib.darwinSystem {
                  modules = [
                    { networking.hostName = machineName; }
                    (self.lib.nixosModule "darwin/base")
                    machineModule
                  ];
                  specialArgs = {
                    inherit self inputs;
                    vars = self.lib.vars;
                    vars' = self.lib.vars.machines.${machineName} or { };
                  };
                };

              nixosModule =
                name:
                if builtins.pathExists ./modules/${name}/default.nix then
                  import ./modules/${name}/default.nix
                else if builtins.pathExists ./modules/${name}.nix then
                  import ./modules/${name}.nix
                else
                  throw "NixOS module '${name}' not found in modules directory";
            };

            overlays = {
              default = import ./overlays/default.nix { inherit inputs; };
              colmena = inputs.colmena.overlays.default;
            };
          };

        perSystem =
          {
            system,
            ...
          }:
          let
            pkgs = import inputs.nixpkgs {
              inherit system;
              overlays = builtins.attrValues inputs.self.overlays;
            };
          in
          {
            legacyPackages = {
              inherit (pkgs) rv32ima;
            };

            devShells.default = pkgs.mkShell {
              packages = with pkgs; [
                openbao
                colmena
                step-cli
              ];
            };
          };
      }
    );
}
