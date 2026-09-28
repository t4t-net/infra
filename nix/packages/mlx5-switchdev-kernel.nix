{ linux, ... }:
# MLX5_CLS_ACT gives VF representors hw-tc-offload in switchdev mode (needed for VF LAG),
# but it depends on NET_TC_SKB_EXT, which the default kernel leaves off.
linux.override (old: {
  kernelPatches = (old.kernelPatches or [ ]) ++ [
    {
      name = "mlx5-switchdev";
      patch = null;
      extraConfig = ''
        NET_TC_SKB_EXT y
        MLX5_CLS_ACT y
      '';
    }
  ];
})
