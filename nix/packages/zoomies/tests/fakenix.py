"""a fake nix/git world 4 driving whole ticks: jobs, wat fails where, nd a log of every call"""
import json
import subprocess
import zlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


class Boom(Exception):
    """stands in 4 zoomies itself breaking mid-run"""


def job(name, eval_error=None, build_ok=True, upload_ok=True, v=""):
    # v changes th hash, like a commit tht actually touched th job
    h = f"{zlib.crc32((name + v).encode()):010d}"
    return {"name": name, "drv": f"/nix/store/{h}-{name}.drv", "out": f"/nix/store/{h}-{name}",
            "eval_error": eval_error, "build_ok": build_ok, "upload_ok": upload_ok}


def fake_world(rev, jobs, crash_on=None, eval_rc=0):
    """returns (run, calls). crash_on is an argv prefix (e.g. ("nix", "copy")) tht raises Boom"""
    calls = []
    built = set()

    def done(argv, rc=0, out="", err=""):
        return subprocess.CompletedProcess(argv, rc, out, err)

    def run(argv):
        calls.append(list(argv))
        if crash_on and tuple(argv[:len(crash_on)]) == tuple(crash_on):
            raise Boom(" ".join(argv))
        if argv[:2] == ["git", "ls-remote"]:
            return done(argv, out=f"{world['rev']}\trefs/heads/main\n")
        if argv[0] == "nix-eval-jobs":
            lines = ["warning: some noise"]
            for j in world["jobs"]:
                if j["eval_error"]:
                    lines.append(json.dumps({"attr": j["name"], "error": j["eval_error"]}))
                else:
                    lines.append(json.dumps({"attr": j["name"], "drvPath": j["drv"], "outputs": {"out": j["out"]}}))
            rc = world["eval_rc"]
            return done(argv, rc=rc, out="\n".join(lines) + "\n", err="eval stderr" if rc else "")
        if argv[:2] == ["nix", "build"]:
            for j in world["jobs"]:
                if f"{j['drv']}^*" in argv and j["build_ok"]:
                    built.add(j["out"])
            failed = any(not j["build_ok"] for j in world["jobs"])
            return done(argv, rc=1 if failed else 0, err="error: build of stuff failed" if failed else "")
        if argv[:2] == ["nix-store", "--check-validity"]:
            bad = [p for p in argv[3:] if p not in built]
            return done(argv, out="".join(p + "\n" for p in bad))
        if argv[:2] == ["nix", "log"]:
            return done(argv, out=f"build log of {argv[2]}\nit exploded\n")
        if argv[:2] == ["nix", "copy"]:
            j = next(j for j in world["jobs"] if j["out"] in argv)
            return done(argv, rc=0 if j["upload_ok"] else 1, err="" if j["upload_ok"] else "403 forbidden")
        if argv[:2] == ["nix-store", "--add-root"]:
            root, path = Path(argv[2]), argv[4]
            root.parent.mkdir(parents=True, exist_ok=True)
            if root.is_symlink():
                root.unlink()
            root.symlink_to(path)
            return done(argv, out=path + "\n")
        raise AssertionError(f"unexpected command {argv}")

    world = {"rev": rev, "jobs": jobs, "eval_rc": eval_rc}
    run.world = world
    return run, calls
