{
  config,
  lib,
  pkgs,
  ...
}:

# pull-based deploys: every few minutes, ask hydra for the latest successful build of this machine's
# toplevel and switch to it. no eval and no git on the box (comin did both, and jj pushes wedged its
# clone), and no ssh session that dies when the switch restarts tailscale.
let
  cfg = config.rv32ima.machine.hydraDeploy;
  hostName = config.networking.hostName;
  discordSecret = "hydra-deploy/discord-webhook";

  deployScript = pkgs.writeShellApplication {
    name = "hydra-deploy";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.curl
      pkgs.jq
      config.nix.package
      config.systemd.package
    ];
    text = ''
      HYDRA_URL=${lib.escapeShellArg cfg.hydraUrl}
      JOB=${lib.escapeShellArg "${cfg.project}/${cfg.jobset}/${cfg.job}"}
      HOST=${lib.escapeShellArg hostName}
      ALLOW_REBOOT=${lib.boolToString cfg.allowReboot}
      WINDOW_LOWER=${lib.escapeShellArg cfg.rebootWindow.lower}
      WINDOW_UPPER=${lib.escapeShellArg cfg.rebootWindow.upper}
      DISCORD_WEBHOOK_FILE=${lib.escapeShellArg (lib.optionalString cfg.discord.enable config.sops.secrets.${discordSecret}.path)}
      # the last path *we* switched to, so a manual colmena apply sticks until hydra has something
      # newer instead of getting reverted on the next tick (or after a reboot). a gc root and not a
      # file in /var/lib, since impermanence wipes that but /nix always survives
      STATE=/nix/var/nix/gcroots/hydra-deploy-last-applied

      # latest and not latest-finished: latest-finished only looks at evals where *every* build is
      # done, so we'd sit waiting on some installer or disk image nobody deploys
      build=$(curl -sfL --max-time 30 -H 'Accept: application/json' "$HYDRA_URL/job/$JOB/latest")
      build_id=$(jq -r '.id' <<<"$build")
      path=$(jq -r 'select(.finished == 1 and .buildstatus == 0) | .buildoutputs.out.path // empty' <<<"$build")

      # don't trust hydra to hand us the right job: a typo'd job name switching pawpatch to
      # psychoboost's system would be a very bad day
      if [[ $path != /nix/store/*-nixos-system-"$HOST"-* ]]; then
        echo "hydra build $build_id gave '$path', which isn't a system for $HOST, refusing" >&2
        exit 1
      fi

      current=$(readlink -f /run/current-system)
      last=$(readlink "$STATE" || true)

      # first run on this box: adopt whatever hydra has instead of deploying it. we got here via
      # colmena, so current-system is what someone meant to run, and hydra may well be older (or not
      # have this module at all yet). from here on only builds newer than this one get deployed
      if [[ -z $last ]]; then
        echo "first run, adopting hydra build $build_id as already applied: $path"
        ln -sfn "$path" "$STATE"
        last=$path
      fi

      if [[ $path == "$current" ]]; then
        ln -sfn "$path" "$STATE"
      elif [[ $path == "$last" ]]; then
        echo "running $current, which isn't hydra's build $build_id, but we already applied that one. leaving it alone"
      else
        echo "deploying hydra build $build_id: $path"
        # signatures are still checked here, so hydra can only point us at things cache.t4t.net signed
        nix-store --realise "$path" >/dev/null
        # switching to a system without us in it uninstalls us, and then only colmena can fix it.
        # turning this off is a manual job anyway
        if [[ ! -e $path/etc/systemd/system/hydra-deploy.timer ]]; then
          echo "hydra build $build_id doesn't have hydra-deploy in it, refusing to deploy it" >&2
          exit 1
        fi
        nix-env --profile /nix/var/nix/profiles/system --set "$path"
        # written before the switch so a switch that keeps failing doesn't get retried (and restart
        # half the box) every tick. the unit going failed is the signal
        ln -sfn "$path" "$STATE"

        # a transient unit, so the switch has its own lifetime that switch-to-configuration can't
        # stop out from under itself. a fixed name doubles as a lock
        systemd-run --unit=hydra-deploy-switch --collect --wait --quiet --service-type=exec \
          -E LOCALE_ARCHIVE -E NIXOS_INSTALL_BOOTLOADER= \
          "$path/bin/switch-to-configuration" switch
      fi

      # checked every tick, not just after a deploy, so a kernel bump that landed outside the
      # window gets its reboot in the next one
      needs_reboot=false
      for f in kernel initrd kernel-modules; do
        if [[ $(readlink -f "/run/booted-system/$f") != $(readlink -f "/run/current-system/$f") ]]; then
          needs_reboot=true
        fi
      done

      if [[ $needs_reboot == true ]]; then
        now=$(date +%H:%M)
        in_window=false
        if [[ $WINDOW_LOWER < "$WINDOW_UPPER" ]]; then
          if [[ ! $now < "$WINDOW_LOWER" && $now < "$WINDOW_UPPER" ]]; then
            in_window=true
          fi
        # window wraps past midnight, like 23:00-01:00
        elif [[ ! $now < "$WINDOW_LOWER" || $now < "$WINDOW_UPPER" ]]; then
          in_window=true
        fi

        # once per pending kernel, not once per tick. /run is a tmpfs, so the reboot itself clears
        # this, and a second kernel bump before then pings again
        pending=$(readlink -f /run/current-system/{kernel,initrd,kernel-modules} | sha256sum | cut -d' ' -f1)
        notified=/run/hydra-deploy/reboot-notified
        if [[ -n $DISCORD_WEBHOOK_FILE && $(cat "$notified" 2>/dev/null || true) != "$pending" ]]; then
          booted_kernel=$(basename "$(dirname "$(readlink -f /run/booted-system/kernel)")")
          new_kernel=$(basename "$(dirname "$(readlink -f /run/current-system/kernel)")")
          if [[ $ALLOW_REBOOT == true ]]; then
            plan="rebooting itself between $WINDOW_LOWER and $WINDOW_UPPER"
          else
            plan="won't reboot itself, someone has to do it by hand"
          fi
          if [[ $booted_kernel == "$new_kernel" ]]; then
            what="same kernel (''${new_kernel#*-}), but a new initrd or kernel modules"
          else
            what="booted ''${booted_kernel#*-}, now has ''${new_kernel#*-}"
          fi
          payload=$(jq -n --arg msg "**$HOST** needs a reboot: $what. $plan" '{content: $msg}')
          # a failed ping isn't a failed deploy, so it just gets retried next tick
          if curl -sf --max-time 10 --retry 3 -H 'Content-Type: application/json' -d "$payload" "$(<"$DISCORD_WEBHOOK_FILE")" >/dev/null; then
            echo "$pending" >"$notified"
          else
            echo "couldn't ping discord about the pending reboot, trying again next tick" >&2
          fi
        fi

        if [[ $ALLOW_REBOOT == true && $in_window == true ]]; then
          echo "kernel changed since boot, rebooting"
          systemctl reboot
        else
          echo "kernel changed since boot, reboot pending (allowReboot=$ALLOW_REBOOT, window $WINDOW_LOWER-$WINDOW_UPPER)"
        fi
      fi
    '';
  };
in
{
  options.rv32ima.machine.hydraDeploy = {
    enable = lib.mkEnableOption "pulling this machine's system from hydra and switching to it";

    hydraUrl = lib.mkOption {
      type = lib.types.str;
      default = "https://hydra.tail09d5b.ts.net";
    };

    project = lib.mkOption {
      type = lib.types.str;
      default = "infra";
    };

    jobset = lib.mkOption {
      type = lib.types.str;
      default = "main";
    };

    job = lib.mkOption {
      type = lib.types.str;
      default = "nixos.${hostName}";
      defaultText = lib.literalExpression ''"nixos.''${config.networking.hostName}"'';
    };

    interval = lib.mkOption {
      type = lib.types.str;
      default = "2min";
      description = "How often to ask hydra for a new build (systemd time span).";
    };

    allowReboot = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Reboot inside rebootWindow when the kernel, initrd or kernel modules changed since boot.";
    };

    discord.enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Ping discord (webhook from secrets/hydra-deploy.yaml) once when a reboot is pending.";
    };

    rebootWindow = {
      lower = lib.mkOption {
        type = lib.types.strMatching "[[:digit:]]{2}:[[:digit:]]{2}";
        default = "03:00";
      };
      upper = lib.mkOption {
        type = lib.types.strMatching "[[:digit:]]{2}:[[:digit:]]{2}";
        default = "05:00";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    sops.secrets.${discordSecret} = lib.mkIf cfg.discord.enable {
      sopsFile = ../../secrets/hydra-deploy.yaml;
      key = "discord-webhook";
    };

    systemd.services.hydra-deploy = {
      description = "deploy this machine's latest hydra build";
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      # the switch would otherwise restart (i.e. kill) the thing doing the switching
      restartIfChanged = false;
      unitConfig.X-StopOnRemoval = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe deployScript;
        # holds the reboot-notified marker; kept between ticks, gone after a reboot
        RuntimeDirectory = "hydra-deploy";
        RuntimeDirectoryPreserve = true;
      };
    };

    systemd.timers.hydra-deploy = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "2min";
        OnUnitInactiveSec = cfg.interval;
      };
    };
  };
}
