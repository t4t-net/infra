"""one zoomies tick: poll th branch, eval, build, upload, publish latest/<job>.json, ping discord.

every side effect goes thru params (run, now, post, state_dir) so th tests can drive a whole run
w a fake nix. see DESIGN.md "th contract" 4 th file shapes, they r load-bearing 4 hydra-deploy.
"""
import fcntl
import html
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LOG_TAIL_LINES = 200


def load_config(path):
    cfg = json.loads(Path(path).read_text())
    cfg.setdefault("branch", "main")
    cfg.setdefault("flake_dir", "")
    cfg.setdefault("flake_attr", "hydraJobs")
    cfg.setdefault("eval_workers", 4)
    cfg.setdefault("eval_max_memory_mb", 4096)
    cfg.setdefault("discord_webhook_file", None)
    cfg.setdefault("public_url", "")
    cfg.setdefault("keep_runs", 50)
    for k in ("repo", "state_dir", "store_uri"):
        if not cfg.get(k):
            raise ValueError(f"config is missing {k!r}")
    return cfg


# --- real side effects (only main() wires these in) ---

def real_run(argv):
    """run a command, capture its output, nd echo stderr so it still lands in th journal"""
    p = subprocess.run(argv, capture_output=True, text=True, errors="replace")
    if p.stderr:
        sys.stderr.write(p.stderr)
    return p


def real_post(url, body):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "zoomies"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


# --- small file helpers ---

def write_atomic(path, text):
    """tmp + rename so th static file server never hands out half a file"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def write_json(path, obj):
    write_atomic(path, json.dumps(obj, indent=1, sort_keys=True) + "\n")


def read_text(path, default=None):
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return default


def safe_job(job):
    """job names become file names, so nothing tht could climb out of th dir"""
    return bool(job) and "/" not in job and "\0" not in job and not job.startswith(".")


def tail(text, n=LOG_TAIL_LINES):
    return "\n".join((text or "").splitlines()[-n:])


def flake_ref(repo, branch, rev, flake_dir, attr):
    if repo.startswith("/"):
        base = "git+file://" + repo
    elif "://" in repo and not repo.startswith("git+"):
        base = "git+" + repo
    else:
        base = repo
    # ref= too, else nix only fetches th default branch nd cant find a rev tht lives elsewhere
    q = f"ref={branch}&rev={rev}" + (f"&dir={flake_dir}" if flake_dir else "")
    return f"{base}?{q}#{attr}"


# --- pipeline steps ---

def ls_remote(run, repo, branch):
    p = run(["git", "ls-remote", repo, f"refs/heads/{branch}"])
    if p.returncode != 0:
        raise RuntimeError(f"git ls-remote failed ({p.returncode}): {tail(p.stderr, 5)}")
    for line in p.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/heads/{branch}":
            return sha.strip()
    raise RuntimeError(f"branch {branch} not found in {repo}")


def evaluate(run, cfg, rev, roots_dir):
    """nix-eval-jobs streams 1 json line per job, so 1 broken job is just an error 4 tht job.
    returns (jobs, eval_rc, eval_stderr) where jobs = {attr: {"drv", "outputs"} or {"error"}}"""
    argv = ["nix-eval-jobs",
            "--flake", flake_ref(cfg["repo"], cfg["branch"], rev, cfg["flake_dir"], cfg["flake_attr"]),
            "--workers", str(cfg["eval_workers"]),
            "--max-memory-size", str(cfg["eval_max_memory_mb"]),
            # hydraJobs is plain nested attrsets w no recurseForDerivations
            "--force-recurse",
            # roots so th drvs cant get gc'd between eval nd build
            "--gc-roots-dir", str(roots_dir)]
    p = run(argv)
    jobs = {}
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        attr = j.get("attr")
        if not attr:
            continue
        if j.get("error"):
            jobs[attr] = {"error": j["error"]}
        elif j.get("drvPath") and j.get("outputs"):
            jobs[attr] = {"drv": j["drvPath"], "outputs": j["outputs"]}
        else:
            jobs[attr] = {"error": "nix-eval-jobs gave no drvPath/outputs:\n" + line}
    return jobs, p.returncode, p.stderr


def main_output(outputs):
    return outputs.get("out") or outputs[sorted(outputs)[0]]


def build(run, drvs):
    """1 nix build 4 everything so th daemon schedules it all; per-job result is checked after"""
    if not drvs:
        return ""
    p = run(["nix", "build", "--keep-going", "--no-link"] + [f"{d}^*" for d in drvs])
    return p.stderr


def invalid_paths(run, paths):
    if not paths:
        return set()
    p = run(["nix-store", "--check-validity", "--print-invalid"] + list(paths))
    if p.returncode != 0:
        raise RuntimeError(f"nix-store --check-validity failed: {tail(p.stderr, 5)}")
    return set(p.stdout.split())


def build_log(run, drv, build_stderr):
    p = run(["nix", "log", drv])
    if p.returncode == 0 and p.stdout.strip():
        return p.stdout
    # no log usually means a dependency failed nd this drv never started
    return ("no build log 4 " + drv + " (a dependency probably failed)\n\ntail of nix build:\n"
            + tail(build_stderr))


def upload(run, store_uri, paths):
    p = run(["nix", "copy", "--to", store_uri] + list(paths))
    return p.returncode == 0, p.stderr


def add_gcroot(run, root, path):
    Path(root).parent.mkdir(parents=True, exist_ok=True)
    # root outside /nix/var/nix/gcroots = indirect root, th symlink itself keeps th path alive
    p = run(["nix-store", "--add-root", str(root), "--realise", path])
    if p.returncode != 0:
        raise RuntimeError(f"gc root 4 {path} failed: {tail(p.stderr, 5)}")


# --- reporting ---

def render_index(info, has_eval_log):
    rows = []
    for job in sorted(info["jobs"]):
        r = info["jobs"][job]
        log = ""
        if r.get("log"):
            log = f'<a href="{html.escape(urllib.parse.quote(r["log"]))}">log</a>'
        path = html.escape(r.get("path") or "")
        rows.append(f"<tr><td>{html.escape(job)}</td><td>{html.escape(r['status'])}</td>"
                    f"<td>{log}</td><td><code>{path}</code></td></tr>")
    eval_log = '<p><a href="logs/eval.log">nix-eval-jobs stderr</a></p>' if has_eval_log else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>zoomies run {info['run']}</title></head>
<body>
<h1>zoomies run {info['run']}</h1>
<p>rev <code>{html.escape(info['rev'])}</code>, state {html.escape(info['state'])},
<a href="run.json">run.json</a></p>
{eval_log}
<table>
<tr><th>job</th><th>status</th><th>log</th><th>path</th></tr>
{chr(10).join(rows)}
</table>
</body></html>
"""


def discord_message(info, public_url, eval_rc):
    ok = sorted(j for j, r in info["jobs"].items() if r["status"] == "ok")
    failed = sorted(j for j, r in info["jobs"].items() if r["status"] != "ok")
    link = f"{public_url.rstrip('/')}/runs/{info['run']}/"
    if info["state"] == "crashed":
        return f"zoomies run {info['run']} `{info['rev'][:12]}` crashed, see th journal on psychoboost. {link}"
    msg = f"zoomies run {info['run']} `{info['rev'][:12]}`: {len(ok)} ok, {len(failed)} failed"
    if eval_rc:
        msg += f" (nix-eval-jobs exited {eval_rc})"
    if failed:
        names = ", ".join(failed)
        if len(names) > 1500:
            names = names[:1500] + "..."
        msg += f"\nfailed: {names}"
    return msg + f"\n{link}"


def notify(post, webhook_file, text):
    """discord is nice 2 have, never worth failing a run over"""
    if not webhook_file:
        return
    try:
        url = Path(webhook_file).read_text().strip()
        post(url, json.dumps({"content": text}).encode())
    except Exception as e:  # noqa: BLE001
        print(f"zoomies: discord ping failed: {type(e).__name__}", file=sys.stderr)


def prune(runs_dir, keep):
    ids = sorted((int(d.name) for d in Path(runs_dir).iterdir() if d.is_dir() and d.name.isdigit()),
                 reverse=True)
    for old in ids[keep:]:
        shutil.rmtree(Path(runs_dir) / str(old))


# --- th tick ---

def do_run(cfg, run, now, rid, rev, run_dir, info, write_run, roots_dir):
    """eval → build → upload → gc root → publish. fills info["jobs"] w only final statuses,
    so a crash leaves run.json w just th jobs we actually know about"""
    state = Path(cfg["state_dir"])
    logs = run_dir / "logs"

    def fail(job, status, text, drv=None):
        log = None
        if safe_job(job):
            write_atomic(logs / f"{job}.log", text)
            log = f"logs/{job}.log"
        info["jobs"][job] = {"status": status, "drv": drv, "path": None, "log": log}

    evaluated, eval_rc, eval_err = evaluate(run, cfg, rev, roots_dir)
    if eval_rc != 0:
        write_atomic(logs / "eval.log", eval_err)
    jobs = {}
    for job, j in evaluated.items():
        if not safe_job(job):
            fail(job, "eval-failed", "")
        elif "error" in j:
            fail(job, "eval-failed", j["error"])
        else:
            jobs[job] = j
    write_run()

    build_err = build(run, sorted({j["drv"] for j in jobs.values()}))
    invalid = invalid_paths(run, sorted({p for j in jobs.values() for p in j["outputs"].values()}))
    built = {}
    for job, j in sorted(jobs.items()):
        if invalid & set(j["outputs"].values()):
            fail(job, "build-failed", build_log(run, j["drv"], build_err), j["drv"])
        else:
            built[job] = j
    write_run()

    uploaded = {}
    for job, j in sorted(built.items()):
        ok, err = upload(run, cfg["store_uri"], sorted(j["outputs"].values()))
        if ok:
            uploaded[job] = j
        else:
            fail(job, "upload-failed", "nix copy failed:\n" + tail(err), j["drv"])
    write_run()

    for job, j in sorted(uploaded.items()):
        add_gcroot(run, state / "gcroots" / job, main_output(j["outputs"]))

    # publish last nd all at once, so a crash above leaves every latest/ file untouched
    published_at = now()
    for job, j in sorted(uploaded.items()):
        path = main_output(j["outputs"])
        write_json(state / "public" / "latest" / f"{job}.json",
                   {"run": rid, "rev": rev, "job": job, "path": path, "finished_at": published_at})
        info["jobs"][job] = {"status": "ok", "drv": j["drv"], "path": path, "log": None}
    return eval_rc


def tick(cfg, run, now, post):
    """1 timer tick. returns 0 if nothing 2 do or th run finished (even w failed jobs);
    raises if zoomies itself broke, after marking th run crashed"""
    state = Path(cfg["state_dir"])
    (state / "state").mkdir(parents=True, exist_ok=True)
    lock = open(state / "state" / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("zoomies: another tick is still going, skipping", file=sys.stderr)
        lock.close()
        return 0
    try:
        return _tick_locked(cfg, run, now, post, state)
    finally:
        lock.close()


def _tick_locked(cfg, run, now, post, state):
    runs_dir = state / "public" / "runs"
    last_id = int(read_text(state / "state" / "last-id", "0"))
    last_run = None
    if last_id:
        try:
            last_run = json.loads((runs_dir / str(last_id) / "run.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            last_run = None
    # we hold th lock, so a "running" run is one tht got killed b4 its finally could fire
    if last_run and last_run.get("state") == "running":
        last_run["state"] = "crashed"
        write_json(runs_dir / str(last_id) / "run.json", last_run)

    rev = ls_remote(run, cfg["repo"], cfg["branch"])
    if rev == read_text(state / "state" / "last-rev") and (last_run is None or last_run.get("state") == "done"):
        return 0

    # th id is claimed b4 any work, so even a crashed run burns it nd ids only go up
    rid = last_id + 1
    write_atomic(state / "state" / "last-id", f"{rid}\n")
    run_dir = runs_dir / str(rid)
    run_dir.mkdir(parents=True, exist_ok=True)
    info = {"run": rid, "rev": rev, "started_at": now(), "finished_at": None, "state": "running", "jobs": {}}

    def write_run():
        write_json(run_dir / "run.json", info)

    write_run()
    roots_dir = state / "state" / "eval-roots"
    shutil.rmtree(roots_dir, ignore_errors=True)
    roots_dir.mkdir(parents=True)
    done = False
    try:
        eval_rc = do_run(cfg, run, now, rid, rev, run_dir, info, write_run, roots_dir)
        info["state"] = "done"
        info["finished_at"] = now()
        write_atomic(run_dir / "index.html", render_index(info, (run_dir / "logs" / "eval.log").exists()))
        write_run()
        write_atomic(state / "state" / "last-rev", f"{rev}\n")
        done = True
    finally:
        shutil.rmtree(roots_dir, ignore_errors=True)
        if not done:
            info["state"] = "crashed"
            info["finished_at"] = now()
            write_run()
            write_atomic(run_dir / "index.html", render_index(info, False))
            # a rev tht crashes every tick would ping every 2 min, so only ping th first crash
            if not (last_run and last_run.get("state") == "crashed" and last_run.get("rev") == rev):
                notify(post, cfg["discord_webhook_file"], discord_message(info, cfg["public_url"], 0))
    notify(post, cfg["discord_webhook_file"], discord_message(info, cfg["public_url"], eval_rc))
    prune(runs_dir, cfg["keep_runs"])
    return 0
