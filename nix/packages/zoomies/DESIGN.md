# zoomies: a tiny ci 2 replace hydra

## why

hydra is a perl web app + postgres + a queue runner, built 4 hydra.nixos.org's scale. we use
1 jobset (infra/main), ~34 jobs, 1 builder (psychoboost on localhost) nd 1 R2 bucket. in
november 2026 it cost us a path traversal in `/log` (GHSA-rqvm-hhh5-vrx7), then an outage:
unstable's hydra is a rust rewrite w gRPC builders tht doesnt fit 26.05's module, nd its
hydra-init migrated th db 2 schema 88 b4 crashing. thats a lot of moving parts 4 "build main,
upload it, tell th fleet".

## wat th fleet actually needs from hydra

th whole contract is 2 json endpoints:

- `GET /job/infra/main/nixos.<host>/latest`: hydra-deploy reads `.id`, `.finished`,
  `.buildstatus`, `.buildoutputs.out.path`. it needs `.id` 2 only ever go up (rollback check).
  th discord ping links `/build/<id>`.
- `GET /job/infra/main/nixos.<host>-installer/latest-finished`: th netboot bootstrapper reads
  `.buildoutputs.out.path`.

plus th side effect: every output is signed nd in `s3://rv32ima-nix-store` (cache.t4t.net).

zoomies doesnt copy hydra's url shape. it serves its own simpler contract at
`https://zoomies.tail09d5b.ts.net/` (a tailscale service on psychoboost), nd hydra-deploy + th
bootstrapper move over 2 it at cutover.

## th contract (static files, all json is utf-8, keys exactly as written)

`latest/<job>.json`, e.g. `latest/nixos.iris.json`, `latest/nixos.iris-installer.json`. `<job>`
is th nix-eval-jobs attr name of th `hydraJobs` output (`nixos.iris`,
`packages.x86_64-linux.colmena`, ...):

```json
{"run": 213, "rev": "<full git sha>", "job": "nixos.iris",
 "path": "/nix/store/...-nixos-system-iris-...", "finished_at": 1795700000}
```

it exists only once th job built AND its closure is uploaded + signed. `run` only ever goes up
(th agent's rollback check uses it instead of hydra's build id). a job tht failed in a later run
keeps its old file.

`runs/<run>/run.json`:

```json
{"run": 213, "rev": "<sha>", "started_at": 1795699000, "finished_at": 1795700000,
 "state": "running" | "done" | "crashed",
 "jobs": {"nixos.iris": {"status": "ok" | "eval-failed" | "build-failed" | "upload-failed",
                         "drv": "/nix/store/...drv" | null, "path": "/nix/store/..." | null,
                         "log": "logs/nixos.iris.log" | null}}}
```

`runs/<run>/index.html` lists th jobs nd links their logs. `runs/<run>/logs/<job>.log` holds
eval errors or `nix log <drv>` 4 failed jobs. discord pings link `runs/<run>/`.

## non-goals (4 nao)

no web ui, no PR checks, no multiple projects/jobsets, no remote builder protocol (nix-daemon
already does remote builds from /etc/nix/machines), no db, no user accounts.

## how a run goes

a systemd timer on psychoboost (every ~2 min) runs `zoomies run`:

1. `git ls-remote` th repo 4 main. same commit as th last run → done. (polling, no webhook:
   nothing inbound, nd 1-2 min is as fast as hydra is today.)
2. new commit → new run id = last id + 1, stored in `state/last-id`. every run gets a dir
   `runs/<id>/` w `run.json` (commit, start/end, per-job results) as it goes.
3. eval: `nix-eval-jobs --flake github:t4t-net/infra/<rev>?dir=nix#hydraJobs` w workers nd a
   memory cap like hydra's (4 x 4G). it streams 1 json line per job, so 1 broken job is just
   an error 4 tht job nd th rest keep going.
4. build: `nix build --keep-going` on th drvs. a job's result is th exit status of its own drv.
5. upload: `nix copy --to <store uri w secret-key>` per successful job. signing happens here,
   same as hydra's `store_uri` today.
6. publish: 4 every job tht built AND uploaded, write `latest/<job>.json` (tmp file + rename,
   so a reader never sees half a file). a failed job keeps its old file, like hydra's `/latest`.
7. logs: failed jobs get `nix log <drv>` saved 2 `runs/<id>/logs/<job>.log`.
8. report: 1 discord message per run (commit, ok/failed counts, failed job names), using th
   webhook hydra-deploy already has.


a run tht crashes halfway leaves `run.json` marked unfinished nd publishes nothing it didnt
finish. th next tick starts over on th same commit (th id still goes up, ids r cheap).

retries: `state/last-rev` only moves once a run counts. a crash, a whole-eval failure
(nix-eval-jobs exits non-zero), or any upload-failed job means th next tick retries th same commit
w a new id (1 discord ping per commit 4 those); per-job eval errors nd build failures r real
failures nd dont retry.

## layout

```
/var/lib/zoomies/
  state/last-id  state/last-rev        (not served)
  public/latest/<job>.json             (served)
  public/runs/<id>/run.json  index.html  logs/<job>.log   (served)
  gcroots/<job> -> current published path
```

only `public/` is served, read-only as static files (nginx `root`, autoindex off), via
`rv32ima.machine.tailscale.services.zoomies` → zoomies.tail09d5b.ts.net. gc roots keep th published path per job alive on psychoboost. old runs/ get pruned
after N runs.

## security

no request parsing beyond a static file server. th only input is our own repo's main. zoomies
runs as its own user. th signing key nd R2 creds r readable by tht user only, nd th files it
serves never include them (state/ nd th key live outside th served dirs).

## tui: `zoomies status`

runs on ellie's laptop. 4 each host in a config list it shows: published path + run id (from
`latest/nixos.<host>.json` over th tailnet), wat th host runs (`ssh root@host readlink /run/current-system`), th
agent's last result (`systemctl show hydra-deploy -p Result,ExecMainExitTimestamp`), nd
whether a reboot is pending. hosts w a mismatch or a failed agent float 2 th top. refreshes
every N seconds, curses from stdlib. ssh calls run in parallel w a timeout so 1 dead host
doesnt freeze it. no new endpoint on th fleet.

## code

python 3, stdlib only, packaged like forever-ah (`buildPythonApplication`, unittest in
checkPhase). th nix commands, git, discord, clock nd filesystem root get passed in as
params, never module globals, so tests drive a full run w a fake nix nd assert stuff like:
a failed job keeps its old `latest`, ids only go up, a crash mid-run publishes nothing
half-done, 1 eval error doesnt sink th other jobs.

## cutover

1. deploy zoomies on psychoboost next 2 hydra, publishing 2 th same bucket (same signing key,
   so th outputs r identical).
2. 4 a few commits, diff zoomies' `latest/<job>.json` paths against hydra's `/latest` 4 every
   job. they should match.
3. flip hydra-deploy nd th bootstrapper 2 zoomies (an option on th agent picks th source, so
   hosts can move 1 at a time).
4. turn hydra off. keep /var/lib/postgresql nd /var/lib/hydra 4 a while in case we want history.
5. rename `hydraDeploy` 2 something honest once hydra is gone.

## decided

name stays zoomies (2026-11-25). served at zoomies.tail09d5b.ts.net. hydra's url shape is
dropped 4 th contract above.
