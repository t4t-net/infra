{
  config,
  lib,
  pkgs,
  inputs,
  ...
}:
{
  options = {
    rv32ima.machine.tailscale.enable = lib.mkEnableOption "tailscale";
    rv32ima.machine.tailscale.services = lib.mkOption {
      type = lib.types.attrsOf (
        lib.types.submodule (
          { config, ... }:
          {
            options = {
              name = lib.mkOption {
                type = lib.types.str;
                default = config._module.args.name;
              };
              listenTypes = lib.mkOption {
                type = lib.types.listOf (
                  lib.types.submodule {
                    options = {
                      type = lib.mkOption {
                        type = lib.types.str;
                      };
                      port = lib.mkOption {
                        type = lib.types.port;
                      };
                      targetPort = lib.mkOption {
                        type = lib.types.port;
                      };
                    };
                  }
                );
                default = [
                  {
                    type = "https";
                    port = 443;
                    targetPort = config.port;
                  }
                ];
              };
              tag = lib.mkOption {
                type = lib.types.str;
                default = config.name;
              };
              # Kept for backwards compatibility
              port = lib.mkOption {
                type = lib.types.port;
              };
              targetUnit = lib.mkOption {
                type = lib.types.str;
                default = "${config.name}.service";
              };
            };

          }
        )
      );
      default = { };
    };
  };

  config = lib.mkIf config.rv32ima.machine.tailscale.enable {
    services.tailscale.enable = true;
    services.tailscale.package =
      let
        pkgsUnstable = import inputs.nixpkgs-unstable {
          system = pkgs.stdenv.hostPlatform.system;
        };
      in
      pkgsUnstable.tailscale;
    services.tailscale.openFirewall = true;
    services.tailscale.useRoutingFeatures = "both";
    services.tailscale.extraSetFlags = [ "--accept-routes" ];
    networking.firewall.trustedInterfaces = [ "tailscale0" ];

    systemd.services = lib.concatMapAttrs (
      _:
      {
        name,
        tag,
        targetUnit,
        listenTypes,
        # Ignore the port argument we get
        ...
      }:
      builtins.listToAttrs (
        map (
          x:
          lib.nameValuePair "${name}-serve-${toString x.targetPort}" {
            wantedBy = [ "multi-user.target" targetUnit ];
            after = [
              targetUnit
              "tailscaled.service"
            ];
            wants = [
              "tailscaled.service"
            ];
            unitConfig = {
              BindsTo = [ targetUnit ];
            };
            path = [
              config.services.tailscale.package
            ];
            serviceConfig = {
              RemainAfterExit = "yes";
              Type = "oneshot";
              ExecStart = pkgs.writeShellScript "${name}-serve" ''
                tailscale wait
                ${pkgs.flock}/bin/flock /tmp/tailscale-serve.lock -c "tailscale serve --service=svc:${tag} --${x.type}=${toString x.port} ${builtins.toString x.targetPort}"
              '';
              ExecStop = pkgs.writeShellScript "${name}-serve-clear" ''
                ${pkgs.flock}/bin/flock /tmp/tailscale-serve.lock -c "tailscale serve --service=svc:${tag} --${x.type}=${toString x.port} off"
              '';
            };
          }
        ) listenTypes
      )
    ) config.rv32ima.machine.tailscale.services;
  };
}
