{
  config,
  lib,
  pkgs,
  ...
}:
let
  # closed source, so pin th digest nd not just th tag. tags on ghcr can move
  image = "ghcr.io/peonist-ai/halogen-flash-server:0.21.0@sha256:382e8296ff68fcd7deda7847a3bf4b55882d31041bec6bfb2dffe4ea9bb90de6";
  weightsRepo = "peonist-ai/halogen-qwen3.8-flash-next";
  weightsRevision = "3842e1096091b74d1e62c1651bc6cf88dd6e063b";
  stateDir = "/var/lib/halogen";
  modelDir = "${stateDir}/models";
  fetchedMarker = "${modelDir}/.${weightsRevision}";
  # th same UD-Q4_K_XL llama-cpp serves. halogen repacks it into its own layout at startup, losslessly
  ggufDir = "/var/lib/llama-models/UD-Q4_K_XL";
  ggufFile = "Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf";
  port = 8731;
in
{
  config = {
    rv32ima.machine.impermanence.extraPersistDirectories = [
      {
        path = /var/lib/halogen;
        mode = "0755";
        owner = "root";
        group = "root";
      }
    ];

    # a GGUF carries no draft head halogen can run, so it needs th 1.4GiB head + tokenizer from th
    # weights repo. fetching them here keeps HALOGEN_DOWNLOAD unset, so th container makes no
    # outbound connections. by hand, like llama-model-fetch:
    #   systemctl start --no-block halogen-model-fetch
    systemd.services.halogen-model-fetch = {
      description = "fetch ${weightsRepo} draft head nd tokenizer";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        TimeoutStartSec = "infinity";
      };
      script = ''
        # named files, not --include: hf's --include takes 1 pattern, nd a 2nd one is read as a filename
        ${lib.getExe' pkgs.python3Packages.huggingface-hub "hf"} download ${weightsRepo} \
          qwen38-flash-next-mtp.hgn \
          tokenizer/chat_template.jinja \
          tokenizer/generation_config.json \
          tokenizer/merges.txt \
          tokenizer/tokenizer.json \
          tokenizer/tokenizer_config.json \
          tokenizer/vocab.json \
          --revision ${weightsRevision} \
          --local-dir ${modelDir}
        mkdir -p ${stateDir}/cache
        touch ${fetchedMarker}
      '';
    };

    virtualisation.oci-containers.containers.halogen = {
      inherit image;
      # it cant share th box w llama-cpp, so halogen is th one tht boots nd llama-cpp is a by-hand swap:
      #   systemctl start llama-cpp        (stops halogen)
      #   systemctl start podman-halogen   (stops llama-cpp)
      autoStart = true;
      cmd = [ "all" ];
      volumes = [
        "${ggufDir}:/gguf:ro"
        "${modelDir}:/models:ro"
        "${stateDir}/cache:/cache"
        "${config.sops.secrets."llama-cpp/api-key".path}:/run/secrets/api-key:ro"
      ];
      environment = {
        HALOGEN_CHECKPOINT = "/gguf/${ggufFile}";
        HALOGEN_MTP_HEAD = "/models/qwen38-flash-next-mtp.hgn";
        HALOGEN_TOKENIZER = "/models/tokenizer";
        # th same key as llama-cpp, so hermes only needs a new base_url
        HALOGEN_API_KEY_FILE = "/run/secrets/api-key";
        HALOGEN_API_PORT = toString port;
        # turns survive a restart instead of re-reading th whole conversation
        HALOGEN_CACHE_DIR = "/cache";
        # a 2nd request gets its own slot instead of evicting th first one's context
        HALOGEN_KV_SLOTS = "2";
        # one full 262k conversation resident, or both slots at 131k
        HALOGEN_KV_POOL_POSITIONS = "262144";
        # th K-quant gguf holds 78-80GiB of weights, nd at th default 32768 th last pin lands under
        # halogen's 16GiB floor on a ~122GiB box (upstream issue #80). costs ~9% prefill
        HALOGEN_MAX_TOK = "16384";
        # th template defaults 2 xhigh, which thinks 4 thousands of tokens on agent prompts
        HALOGEN_REASONING_EFFORT = "low";
        # mlock th weights. unlocked, th kernel reclaims weight pages 4 lookup table rows nd th gpu
        # has 2 remap them: 1.9-3.1s of "GPU queues evicted" per request on th first bench
        HALOGEN_WEIGHTS_LOCK = "1";
      };
      extraOptions = [
        # host networking so th firewall still applies. podman's published ports get DNAT'd past
        # th INPUT chain, which would put th api on th lan. th unauthenticated engine port (8730)
        # binds 127.0.0.1 by default
        "--network=host"
        "--device=/dev/kfd"
        "--device=/dev/dri"
        "--ipc=host"
        "--ulimit=memlock=-1:-1"
        # th engine flushes th last turn 2 th disk cache on SIGTERM
        "--stop-timeout=60"
        # asks th engine 4 a PONG, a bare tcp connect stays green on a wedged gpu queue
        "--health-cmd=/usr/local/bin/halogen-healthcheck api"
        "--health-interval=10s"
        "--health-timeout=35s"
        "--health-retries=3"
        "--health-start-period=20m"
      ];
    };

    # compaction can still move mlocked pages, which costs th same remap as reclaiming them. only
    # mlocked pages care, nd llama-cpp doesnt mlock, so its fine 2 leave on wen llama-cpp is th one up
    boot.kernel.sysctl."vm.compact_unevictable_allowed" = 0;

    systemd.services.podman-halogen = {
      unitConfig.ConditionPathExists = fetchedMarker;
      conflicts = [ "llama-cpp.service" ];
      # podman pulls th image on first start
      serviceConfig.TimeoutStartSec = lib.mkForce "30min";
      after = [ "llama-cpp.service" ];
    };

    # both on at boot would just race 2 c who gets stopped
    systemd.services.llama-cpp.wantedBy = lib.mkForce [ ];

    # https://llm.tail09d5b.ts.net, so clients dont care which engine or port is behind it
    rv32ima.machine.tailscale.services.llm = {
      inherit port;
      targetUnit = "podman-halogen.service";
    };
  };
}
