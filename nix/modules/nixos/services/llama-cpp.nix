{
  config,
  lib,
  pkgs,
  ...
}:
let
  repo = "unsloth/Qwen3.8-Flash-Next-GGUF";
  revision = "766911a6b7369840a91dbcd95f9f997acaab6cd6";
  quant = "UD-Q4_K_XL";
  modelDir = "/var/lib/llama-models";
  fetchedMarker = "${modelDir}/.${revision}-${quant}";
in
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/llama-models;
        mode = "0755";
        owner = "root";
        group = "root";
      }
    ];

    # ~111GB, so this only runs when started by hand. if it hung off llama-cpp, a deploy
    # would sit waiting on th download:
    #   systemctl start --no-block llama-model-fetch
    systemd.services.llama-model-fetch = {
      description = "fetch ${repo} ${quant}";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      onSuccess = [ "llama-cpp.service" ];
      serviceConfig = {
        Type = "oneshot";
        TimeoutStartSec = "infinity";
      };
      script = ''
        ${lib.getExe' pkgs.python3Packages.huggingface-hub "hf"} download ${repo} \
          --revision ${revision} \
          --include "${quant}/*" \
          --local-dir ${modelDir}
        touch ${fetchedMarker}
      '';
    };

    sops.secrets."llama-cpp/api-key" = {
      sopsFile = ../../../machines/nixos/experimental-skin/secrets/llama-cpp.yaml;
      key = "api-key";
      restartUnits = [ "llama-cpp.service" ];
    };

    services.llama-cpp = {
      enable = true;
      package = pkgs.unstable.llama-cpp-vulkan;
      # nothing but tailscale0 gets thru th firewall on this box
      host = "0.0.0.0";
      port = 8080;
      model = "${modelDir}/${quant}/Qwen3.8-Flash-Next-${quant}-00001-of-00004.gguf";
      extraFlags = [
        "--api-key-file"
        "/run/credentials/llama-cpp.service/api-key"
        "--alias"
        "qwen3.8-flash-next"
        "--gpu-layers"
        "999"
        # auto-fit is reported 2 crash on strix halo w models this big
        "--fit"
        "off"
        # auto load mode keeps th ~28GiB n-gram table in ram. reading it off th ssd on demand needs
        # mmap, nd frees th memory th kv cache needs 2 reach th model's native context
        "--load-mode"
        "mmap"
        "--lazy-mode"
        "on"
        "--ctx-size"
        "262144"
        "--parallel"
        "1"
        "--temp"
        "1.0"
        "--top-p"
        "0.95"
        "--top-k"
        "20"
        "--min-p"
        "0.0"
        "--chat-template-kwargs"
        ''{"reasoning_effort":"medium"}''
      ];
    };

    systemd.services.llama-cpp = {
      unitConfig.ConditionPathExists = fetchedMarker;
      # DynamicUser cant read /run/secrets, so systemd hands it over
      serviceConfig.LoadCredential = "api-key:${config.sops.secrets."llama-cpp/api-key".path}";
      # th mesa shader cache needs somewhere writable, HOME doesnt exist w DynamicUser
      environment.XDG_CACHE_HOME = "/var/cache/llama-cpp";
    };
  };
}
