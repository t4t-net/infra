#!/usr/bin/env bash
# Wait until every @auto-deploy machine's system is in cache.t4t.net, i.e. hydra has built it,
# so colmena only substitutes instead of building (kernels!!) in the deploy.
# usage: wait-for-cache.sh [flake] [timeout-seconds]
set -euo pipefail

FLAKE=${1:-./nix}
TIMEOUT=${2:-10800}
CACHE=${CACHE:-https://cache.t4t.net}
INTERVAL=${INTERVAL:-60}

# nixpkgs spews eval warnings on every `nix eval`, so only show nix's stderr when it actually fails
quiet_eval() {
  local err
  err=$(mktemp)
  if ! nix eval "$@" 2>"$err"; then
    cat "$err" >&2
    rm -f "$err"
    return 1
  fi
  rm -f "$err"
}

# evaluated into variables first: set -e can't see failures inside `< <(...)`, and a failed eval
# must not turn into "no machines, everything is cached"
# shellcheck disable=SC2016 # ${n} is nix, not bash
machines_json=$(quiet_eval --json "$FLAKE#lib.vars.machines" --apply \
  'ms: builtins.filter (n: builtins.elem "auto-deploy" (ms.${n}.deployment.tags or [ ])) (builtins.attrNames ms)')
jobs_json=$(quiet_eval --json "$FLAKE#hydraJobs.nixos" --apply builtins.attrNames)
mapfile -t machines < <(jq -r '.[]' <<<"$machines_json")
mapfile -t jobs < <(jq -r '.[]' <<<"$jobs_json")

if [ ${#machines[@]} -eq 0 ]; then
  echo "found no auto-deploy machines, refusing to wave the deploy through" >&2
  exit 1
fi

declare -A pending
for m in "${machines[@]}"; do
  if ! printf '%s\n' "${jobs[@]}" | grep -qx "$m"; then
    echo "$m is auto-deploy but not in hydraJobs.nixos, so hydra will never cache it" >&2
    exit 1
  fi
  # colmena's own evaluation, not nixosConfigurations: if the two ever drift apart, this waits
  # (and times out) instead of letting colmena rebuild everything on the CI builders
  pending[$m]=$(quiet_eval --raw "$FLAKE#colmenaHive.nodes.$m.config.system.build.toplevel.outPath")
  echo "$m -> ${pending[$m]}"
done

deadline=$((SECONDS + TIMEOUT))
while true; do
  for m in "${!pending[@]}"; do
    hash=$(basename "${pending[$m]}" | cut -d- -f1)
    if curl -sf -o /dev/null "$CACHE/$hash.narinfo"; then
      echo "$m is cached"
      unset "pending[$m]"
    fi
  done

  if [ ${#pending[@]} -eq 0 ]; then
    echo "everything is cached :3"
    exit 0
  fi
  if [ $SECONDS -ge $deadline ]; then
    echo "timed out waiting for hydra to build: ${!pending[*]}" >&2
    exit 1
  fi
  echo "waiting on: ${!pending[*]}"
  sleep "$INTERVAL"
done
