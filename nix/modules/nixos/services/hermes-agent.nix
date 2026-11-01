{ inputs, ... }:
{
  imports = [
    inputs.hermes-agent.nixosModules.default
  ];

  config = {
    services.hermes-agent = {
      enable = true;

      # th whole agent lives in a container nd not just its terminal: terminal.backend = docker
      # skips dangerous-command approvals, nd those buttons r wat stands between a prompt injection
      # nd a bad day
      container.enable = true;

      settings = {
        model = {
          provider = "custom";
          base_url = "http://experimental-skin.tail09d5b.ts.net:8080/v1";
          default = "qwen3.8-flash-next";
        };
        # smart mode asks a model whether a command is safe, nd th model is wat we dont trust here
        approvals.mode = "manual";
      };
    };
  };
}
