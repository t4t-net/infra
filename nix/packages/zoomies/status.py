#!/usr/bin/env python3
# zoomies status: wat zoomies published 4 each host vs wat th host actually runs.
# stdlib only. fetch, ssh nd th clock r params so tests never touch th fleet
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://zoomies.tail09d5b.ts.net"
DEFAULT_HOSTS = [
    "cert-authority",
    "experimental-skin",
    "ghostholding",
    "iris",
    "pawpatch",
    "peer2peer",
    "professional-vengeance",
    "psychoboost",
]

# 1 round trip per host. key=value lines so a missing symlink just leaves a blank value
# instead of shifting every line after it. --timestamp=unix gives "@<secs>", no date parsing
SSH_COMMAND = (
    'echo "current=$(readlink /run/current-system)"; '
    'echo "booted_kernel=$(readlink /run/booted-system/kernel)"; '
    'echo "current_kernel=$(readlink /run/current-system/kernel)"; '
    "systemctl show --timestamp=unix hydra-deploy.service "
    "-p Result -p ExecMainExitTimestamp -p ActiveState"
)

# worst first, so wat needs ellie's eyes is at th top
STATE_ORDER = {
    "unreachable": 0,
    "agent-failed": 1,
    "behind": 2,
    "fetch-error": 3,
    "never-published": 4,
    "in-sync": 5,
}


# --- real io (only used as defaults from main, never at import time) ---


def http_fetch(url, timeout=10):
    """bytes, or None on 404. anything else raises."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def ssh_run(host, timeout=15):
    """stdout of SSH_COMMAND on root@host. raises on failure/timeout."""
    # root@ always: ellie@ gets denied on th fleet. BatchMode so a prompt cant hang us
    proc = subprocess.run(
        [
            "ssh",
            "-o", "ConnectTimeout=5",
            "-o", "BatchMode=yes",
            f"root@{host}",
            SSH_COMMAND,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    # 255 is ssh's own failure. anything else means we got in, so keep th output
    if proc.returncode == 255:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "ssh failed")
    return proc.stdout


# --- parsing ---


def parse_published(raw):
    """latest/<job>.json bytes -> dict w run/rev/path/finished_at, or raises ValueError."""
    data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    if not isinstance(data, dict) or not isinstance(data.get("path"), str):
        raise ValueError("no path in latest json")
    run = data.get("run")
    finished = data.get("finished_at")
    return {
        "run": run if isinstance(run, int) else None,
        "rev": data.get("rev") if isinstance(data.get("rev"), str) else None,
        "path": data["path"],
        "finished_at": finished if isinstance(finished, (int, float)) else None,
    }


def parse_ssh(out):
    """key=value lines -> dict. tolerant of junk lines nd missing keys"""
    kv = {}
    for line in (out or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    exit_ts = None
    ts = kv.get("ExecMainExitTimestamp", "")
    if ts.startswith("@"):
        try:
            exit_ts = int(ts[1:])
        except ValueError:
            pass
    booted, cur_k = kv.get("booted_kernel") or None, kv.get("current_kernel") or None
    return {
        "current": kv.get("current") or None,
        # only flag it when we actually saw both, a half answer isnt a reboot
        "reboot_pending": bool(booted and cur_k and booted != cur_k),
        "result": kv.get("Result") or None,
        "active": kv.get("ActiveState") or None,
        "exit_ts": exit_ts,
    }


# --- gathering ---


def gather_host(host, url, fetch, ssh):
    """everything we know about 1 host. never raises"""
    st = {"host": host, "published": None, "pub_error": None, "running": None, "ssh_error": None}
    try:
        raw = fetch(f"{url.rstrip('/')}/latest/nixos.{host}.json")
        if raw is not None:
            st["published"] = parse_published(raw)
    except Exception as e:  # noqa: BLE001 - a bad host shouldnt sink th table
        st["pub_error"] = short_error(e)
    try:
        st["running"] = parse_ssh(ssh(host))
    except Exception as e:  # noqa: BLE001
        st["ssh_error"] = short_error(e)
    st["state"] = derive_state(st)
    return st


def gather(hosts, url, fetch, ssh, timeout=20):
    """all hosts in parallel. a host still going after `timeout` is marked unreachable"""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(hosts)))
    futs = {h: pool.submit(gather_host, h, url, fetch, ssh) for h in hosts}
    deadline = time.monotonic() + timeout
    out = []
    for h, fut in futs.items():
        try:
            out.append(fut.result(timeout=max(0.0, deadline - time.monotonic())))
        except concurrent.futures.TimeoutError:
            st = {"host": h, "published": None, "pub_error": None, "running": None,
                  "ssh_error": "timed out"}
            st["state"] = derive_state(st)
            out.append(st)
    # dont wait on a hung thread, th next refresh doesnt need it
    pool.shutdown(wait=False, cancel_futures=True)
    return sort_statuses(out)


def short_error(e):
    msg = str(e).strip().splitlines()
    return (msg[-1] if msg else type(e).__name__)[:60]


# --- deriving ---


def derive_state(st):
    run = st.get("running")
    if st.get("ssh_error") or run is None:
        return "unreachable"
    if run["result"] and run["result"] != "success":
        return "agent-failed"
    if st.get("pub_error"):
        return "fetch-error"
    if st.get("published") is None:
        return "never-published"
    if run["current"] != st["published"]["path"]:
        return "behind"
    return "in-sync"


def sort_statuses(statuses):
    return sorted(statuses, key=lambda s: (STATE_ORDER.get(s["state"], 99), s["host"]))


def store_hash(path):
    """/nix/store/<hash>-name -> first 8 of th hash. enough 2 eyeball a match"""
    if not path:
        return "-"
    base = os.path.basename(path.rstrip("/"))
    return base.split("-", 1)[0][:8] or "-"


def fmt_age(secs):
    if secs is None:
        return "-"
    secs = max(0, int(secs))
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return f"{secs // n}{unit}"
    return f"{secs}s"


# --- formatting ---

COLUMNS = ["host", "state", "published", "running", "agent", "reboot", "age"]


def format_row(st, now):
    pub = st.get("published")
    run = st.get("running")
    if pub:
        published = f"r{pub['run'] if pub['run'] is not None else '?'} {store_hash(pub['path'])}"
        age = fmt_age(now - pub["finished_at"]) if pub["finished_at"] is not None else "-"
    else:
        published = st.get("pub_error") and f"err: {st['pub_error']}" or "never"
        age = "-"
    if run:
        running = store_hash(run["current"])
        if run["active"] in ("activating", "reloading"):
            agent = "deploying"
        else:
            agent = run["result"] or "?"
            if run["exit_ts"] is not None:
                agent += f" {fmt_age(now - run['exit_ts'])}"
        reboot = "REBOOT" if run["reboot_pending"] else ""
    else:
        running = "-"
        agent = st.get("ssh_error") or "?"
        reboot = ""
    # "!" marks rows tht want attention, plain ascii so it survives any terminal
    mark = "" if st["state"] == "in-sync" else "!"
    return [mark + st["host"], st["state"], published, running, agent, reboot, age]


def newest_run(statuses):
    runs = [s["published"]["run"] for s in statuses
            if s.get("published") and s["published"]["run"] is not None]
    return max(runs) if runs else None


def format_header(url, statuses, now):
    newest = newest_run(statuses)
    when = time.strftime("%H:%M:%S", time.localtime(now))
    return f"zoomies {url}  refreshed {when}  newest run {'r' + str(newest) if newest else '-'}"


def format_table(statuses, now):
    rows = [COLUMNS] + [format_row(s, now) for s in statuses]
    widths = [max(len(r[i]) for r in rows) for i in range(len(COLUMNS))]
    return ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]


def render_text(url, statuses, now):
    return "\n".join([format_header(url, statuses, now), ""] + format_table(statuses, now)) + "\n"


# --- curses (th only untested bit, keep it thin) ---


def run_tui(stdscr, refresh, url, interval, now):
    import curses

    curses.curs_set(0)
    stdscr.timeout(200)
    lock = threading.Lock()
    snap = {"statuses": None, "at": None, "busy": True}
    wake = threading.Event()
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            with lock:
                snap["busy"] = True
            statuses = refresh()
            with lock:
                snap.update(statuses=statuses, at=now(), busy=False)
            wake.wait(interval)
            wake.clear()

    threading.Thread(target=loop, daemon=True).start()
    try:
        while True:
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                return
            if key in (ord("r"), ord("R")):
                wake.set()
            with lock:
                statuses, at, busy = snap["statuses"], snap["at"], snap["busy"]
            draw(stdscr, url, statuses, at, busy)
    finally:
        stop.set()
        wake.set()


def draw(stdscr, url, statuses, at, busy):
    import curses

    stdscr.erase()
    h, w = stdscr.getmaxyx()
    if statuses is None:
        lines = [f"zoomies {url}", "", "gathering..."]
    else:
        lines = [format_header(url, statuses, at)] + [""] + format_table(statuses, at)
    lines.append("")
    lines.append("q quit  r refresh" + ("  (refreshing)" if busy else ""))
    for y, line in enumerate(lines[:h]):
        attr = curses.A_BOLD if y in (0, 2) else 0
        try:
            # w-1 cuz writing th bottom-right cell raises in curses
            stdscr.addnstr(y, 0, line, max(0, w - 1), attr)
        except curses.error:
            pass
    stdscr.refresh()


# --- cli ---


def parse_args(argv):
    p = argparse.ArgumentParser(prog="zoomies status", description="fleet vs wat zoomies published")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--hosts", default=",".join(DEFAULT_HOSTS),
                   help="comma separated (default: th whole fleet)")
    p.add_argument("--interval", type=float, default=10.0)
    p.add_argument("--once", action="store_true", help="print 1 plain text table nd exit")
    return p.parse_args(argv)


def main(argv, fetch=http_fetch, ssh=ssh_run, now=time.time, out=None, isatty=None):
    args = parse_args(argv)
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    out = out or sys.stdout
    tty = out.isatty() if isatty is None else isatty

    def refresh():
        return gather(hosts, args.url, fetch=fetch, ssh=ssh)

    if args.once or not tty:
        out.write(render_text(args.url, refresh(), now()))
        return 0

    import curses

    curses.wrapper(run_tui, refresh, args.url, args.interval, now)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
