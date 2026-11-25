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

zoomies serves those same paths as static files w th same json shape, so neither th agents
nor th bootstrapper change. cutover is flipping a hostname.

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
6. publish: 4 every job tht built AND uploaded, write `job/infra/main/<job>/latest` nd
   `latest-finished` (tmp file + rename, so a reader never sees half a file). a failed job
   keeps its old files, which is exactly wat hydra's `/latest` does. hydra's ids r per build
   nd zoomies' r per run, but both only go up, nd thts all th agent checks.
7. logs: failed jobs get `nix log <drv>` saved 2 `runs/<id>/logs/<job>.log`.
8. report: 1 discord message per run (commit, ok/failed counts, failed job names), using th
   webhook hydra-deploy already has.

`/build/<id>` gets a generated `index.html` listing th run's jobs nd links 2 their logs, so th
discord links keep working w/o a web app.

a run tht crashes halfway leaves `run.json` marked unfinished nd publishes nothing it didnt
finish. th next tick starts over on th same commit (th id still goes up, ids r cheap).

## layout

```
/var/lib/zoomies/
  state/last-id  state/last-rev
  job/infra/main/<job>/latest            (served)
  job/infra/main/<job>/latest-finished   (served)
  build/<id>/index.html                  (served, symlink 2 runs/<id>/)
  runs/<id>/run.json  runs/<id>/logs/
  gcroots/<job> -> current published path
```

served read-only as static files (nginx `root`, autoindex off) at hydra.tail09d5b.ts.net once
we cut over. gc roots keep th published path per job alive on psychoboost. old runs/ get pruned
after N runs.

## security

no request parsing beyond a static file server. th only input is our own repo's main. zoomies
runs as its own user. th signing key nd R2 creds r readable by tht user only, nd th files it
serves never include them (state/ nd th key live outside th served dirs).

## tui: `zoomies status`

runs on ellie's laptop. 4 each host in a config list it shows: published path + run id (from
`latest` over th tailnet), wat th host runs (`ssh root@host readlink /run/current-system`), th
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

1. deploy zoomies on psychoboost next 2 hydra, serving on a different port, nd publishing 2 th
   same bucket (same signing key, so th outputs r identical).
2. 4 a few commits, diff zoomies' `latest` paths against hydra's 4 every job. they should match.
3. point hydra.tail09d5b.ts.net at zoomies' static root. agents nd bootstrapper dont change.
4. turn hydra off. keep /var/lib/postgresql nd /var/lib/hydra 4 a while in case we want history.
5. later: rename `hydraDeploy`/`hydraUrl` 2 something honest.

## open questions

- name lol
- do we keep th `/job/infra/main/...` url shape 4ever, or move th agents 2 a simpler
  `/latest/<job>.json` after cutover? (keeping it means step 3 is free)
