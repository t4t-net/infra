"""whole ticks against a fake nix: wat gets published, wat doesnt, nd th ids"""
import json
import tempfile
import unittest
from pathlib import Path

from fakenix import Boom, fake_world, job

import run as zrun  # noqa: E402

REV1 = "a" * 40
REV2 = "b" * 40
CONTRACT_KEYS = {"run", "rev", "job", "path", "finished_at"}


class Clock:
    def __init__(self):
        self.t = 1795699000

    def __call__(self):
        self.t += 10
        return self.t


class TickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        hook = self.root / "webhook"
        hook.write_text("https://discord.example/hook\n")
        self.cfg = zrun.load_config(self._config(hook))
        self.posts = []
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def _config(self, hook, **kw):
        p = self.root / "config.json"
        p.write_text(json.dumps({"repo": "https://github.com/t4t-net/infra", "branch": "main",
                                 "flake_dir": "nix", "flake_attr": "hydraJobs",
                                 "state_dir": str(self.root / "zoomies"), "store_uri": "s3://bucket?secret-key=/k",
                                 "eval_workers": 4, "eval_max_memory_mb": 4096,
                                 "discord_webhook_file": str(hook),
                                 "public_url": "https://zoomies.example", "keep_runs": 50, **kw}))
        return p

    def tick(self, run):
        return zrun.tick(self.cfg, run=run, now=self.clock, post=lambda url, body: self.posts.append((url, body)))

    @property
    def state(self):
        return Path(self.cfg["state_dir"])

    def latest(self, name):
        p = self.state / "public" / "latest" / f"{name}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def run_json(self, rid):
        return json.loads((self.state / "public" / "runs" / str(rid) / "run.json").read_text())

    def test_full_success_writes_contract(self):
        run, calls = fake_world(REV1, [job("nixos.iris"), job("nixos.iris-installer")])
        self.assertEqual(self.tick(run), 0)
        got = self.latest("nixos.iris")
        self.assertEqual(set(got), CONTRACT_KEYS)
        self.assertEqual(got["run"], 1)
        self.assertEqual(got["rev"], REV1)
        self.assertEqual(got["job"], "nixos.iris")
        self.assertEqual(got["path"], job("nixos.iris")["out"])
        self.assertIsInstance(got["finished_at"], int)
        info = self.run_json(1)
        self.assertEqual(set(info), {"run", "rev", "started_at", "finished_at", "state", "jobs"})
        self.assertEqual(info["state"], "done")
        self.assertEqual(info["jobs"]["nixos.iris"],
                         {"status": "ok", "drv": job("nixos.iris")["drv"], "path": job("nixos.iris")["out"], "log": None})
        self.assertEqual((self.state / "state" / "last-rev").read_text().strip(), REV1)
        self.assertEqual(Path.readlink(self.state / "gcroots" / "nixos.iris"), Path(job("nixos.iris")["out"]))
        # eval flags + flake ref
        ev = next(c for c in calls if c[0] == "nix-eval-jobs")
        self.assertIn(f"git+https://github.com/t4t-net/infra?ref=main&rev={REV1}&dir=nix#hydraJobs", ev)
        self.assertIn("--force-recurse", ev)
        # 1 discord ping w th link
        self.assertEqual(len(self.posts), 1)
        msg = json.loads(self.posts[0][1])["content"]
        self.assertIn("2 ok, 0 failed", msg)
        self.assertIn("https://zoomies.example/runs/1/", msg)

    def test_nothing_to_do_when_rev_unchanged(self):
        run, calls = fake_world(REV1, [job("nixos.iris")])
        self.tick(run)
        calls.clear()
        self.assertEqual(self.tick(run), 0)
        self.assertEqual([c[:2] for c in calls], [["git", "ls-remote"]])
        self.assertEqual((self.state / "state" / "last-id").read_text().strip(), "1")
        self.assertEqual(len(self.posts), 1)

    def test_build_failure_keeps_old_latest_and_logs(self):
        run, _ = fake_world(REV1, [job("nixos.iris"), job("nixos.pawpatch")])
        self.tick(run)
        before = self.latest("nixos.pawpatch")
        run.world.update(rev=REV2, jobs=[job("nixos.iris"), job("nixos.pawpatch", build_ok=False, v="2")])
        self.tick(run)
        self.assertEqual(self.latest("nixos.pawpatch"), before)
        self.assertEqual(self.latest("nixos.iris")["run"], 2)
        r = self.run_json(2)["jobs"]["nixos.pawpatch"]
        self.assertEqual(r["status"], "build-failed")
        self.assertEqual(r["log"], "logs/nixos.pawpatch.log")
        self.assertIsNone(r["path"])
        log = (self.state / "public" / "runs" / "2" / r["log"]).read_text()
        self.assertIn("it exploded", log)
        msg = json.loads(self.posts[-1][1])["content"]
        self.assertIn("1 ok, 1 failed", msg)
        self.assertIn("nixos.pawpatch", msg)

    def test_eval_error_doesnt_sink_others(self):
        run, calls = fake_world(REV1, [job("nixos.broken", eval_error="error: infinite recursion"), job("nixos.iris")])
        self.tick(run)
        self.assertIsNone(self.latest("nixos.broken"))
        self.assertEqual(self.latest("nixos.iris")["run"], 1)
        r = self.run_json(1)["jobs"]["nixos.broken"]
        self.assertEqual(r, {"status": "eval-failed", "drv": None, "path": None, "log": "logs/nixos.broken.log"})
        self.assertIn("infinite recursion", (self.state / "public/runs/1/logs/nixos.broken.log").read_text())
        build = next(c for c in calls if c[:2] == ["nix", "build"])
        self.assertNotIn("broken", " ".join(build))

    def test_upload_failure_not_published(self):
        run, _ = fake_world(REV1, [job("nixos.iris", upload_ok=False), job("nixos.pawpatch")])
        self.tick(run)
        self.assertIsNone(self.latest("nixos.iris"))
        self.assertFalse((self.state / "gcroots" / "nixos.iris").is_symlink())
        self.assertIsNotNone(self.latest("nixos.pawpatch"))
        r = self.run_json(1)["jobs"]["nixos.iris"]
        self.assertEqual(r["status"], "upload-failed")
        self.assertIn("403", (self.state / "public/runs/1" / r["log"]).read_text())

    def test_run_ids_only_go_up(self):
        run, _ = fake_world(REV1, [job("nixos.iris")])
        self.tick(run)
        run.world["rev"] = REV2
        self.tick(run)
        run.world["rev"] = REV1  # a revert still gets a fresh, bigger id
        self.tick(run)
        self.assertEqual(self.latest("nixos.iris")["run"], 3)
        self.assertEqual(sorted(int(d.name) for d in (self.state / "public/runs").iterdir()), [1, 2, 3])

    def test_crash_mid_run_marks_crashed_and_publishes_nothing(self):
        run, _ = fake_world(REV1, [job("nixos.iris"), job("nixos.pawpatch")])
        self.tick(run)
        before = self.latest("nixos.iris")
        crashy, _ = fake_world(REV2, [job("nixos.iris"), job("nixos.pawpatch")], crash_on=("nix", "copy"))
        with self.assertRaises(Boom):
            self.tick(crashy)
        info = self.run_json(2)
        self.assertEqual(info["state"], "crashed")
        self.assertIsNotNone(info["finished_at"])
        self.assertEqual(self.latest("nixos.iris"), before)
        self.assertEqual(self.latest("nixos.pawpatch")["run"], 1)
        self.assertEqual((self.state / "state" / "last-rev").read_text().strip(), REV1)
        self.assertIn("crashed", json.loads(self.posts[-1][1])["content"])
        # next tick retries th same rev under a new id
        run.world["rev"] = REV2
        self.tick(run)
        self.assertEqual(self.latest("nixos.iris"), {**before, "run": 3, "rev": REV2,
                                                      "finished_at": self.latest("nixos.iris")["finished_at"]})
        self.assertEqual(self.run_json(3)["state"], "done")

    def test_repeated_crash_pings_once(self):
        crashy, _ = fake_world(REV1, [job("nixos.iris")], crash_on=("nix", "build"))
        for _ in range(3):
            with self.assertRaises(Boom):
                self.tick(crashy)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual((self.state / "state" / "last-id").read_text().strip(), "3")

    def test_stale_running_run_gets_marked_crashed(self):
        run, _ = fake_world(REV1, [job("nixos.iris")])
        self.tick(run)
        # pretend run 1 got SIGKILLed while running
        p = self.state / "public/runs/1/run.json"
        p.write_text(json.dumps({**self.run_json(1), "state": "running"}))
        self.tick(run)
        self.assertEqual(self.run_json(1)["state"], "crashed")
        self.assertEqual(self.run_json(2)["state"], "done")

    def test_index_escapes_job_names(self):
        evil = 'nixos.<script>alert("x")</script>'
        run, _ = fake_world(REV1, [job(evil, eval_error="<b>nope</b>"), job("nixos.iris")])
        self.tick(run)
        page = (self.state / "public/runs/1/index.html").read_text()
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("nixos.iris", page)

    def test_job_name_cant_escape_dirs(self):
        run, _ = fake_world(REV1, [job("../../state/last-id", eval_error="x"), job("nixos.iris")])
        self.tick(run)
        self.assertEqual((self.state / "state" / "last-id").read_text().strip(), "1")
        self.assertEqual(self.run_json(1)["jobs"]["../../state/last-id"]["log"], None)

    def test_whole_eval_failure_still_finishes(self):
        run, _ = fake_world(REV1, [], eval_rc=1)
        self.assertEqual(self.tick(run), 0)
        self.assertEqual(self.run_json(1)["state"], "done")
        self.assertIn("eval stderr", (self.state / "public/runs/1/logs/eval.log").read_text())
        self.assertIn("nix-eval-jobs exited 1", json.loads(self.posts[-1][1])["content"])

    def test_pruning_keeps_keep_runs(self):
        self.cfg["keep_runs"] = 3
        run, _ = fake_world(REV1, [job("nixos.iris")])
        for i in range(6):
            run.world["rev"] = f"{i:040d}"
            self.tick(run)
        self.assertEqual(sorted(int(d.name) for d in (self.state / "public/runs").iterdir()), [4, 5, 6])
        self.assertEqual(self.latest("nixos.iris")["run"], 6)

    def test_no_webhook_no_ping(self):
        self.cfg["discord_webhook_file"] = None
        run, _ = fake_world(REV1, [job("nixos.iris")])
        self.tick(run)
        self.assertEqual(self.posts, [])

    def test_discord_failure_doesnt_fail_run(self):
        run, _ = fake_world(REV1, [job("nixos.iris")])

        def broken_post(url, body):
            raise OSError("discord is down")
        self.assertEqual(zrun.tick(self.cfg, run=run, now=self.clock, post=broken_post), 0)
        self.assertEqual(self.run_json(1)["state"], "done")


class FlakeRefTest(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(zrun.flake_ref("/srv/infra", "main", "abc", "", "hydraJobs"),
                         "git+file:///srv/infra?ref=main&rev=abc#hydraJobs")
        self.assertEqual(zrun.flake_ref("git+ssh://git@x/y", "trunk", "abc", "nix", "j"),
                         "git+ssh://git@x/y?ref=trunk&rev=abc&dir=nix#j")


class CliTest(unittest.TestCase):
    def test_status_is_lazy(self):
        import sys
        import zoomies
        sys.modules.pop("status", None)
        with self.assertRaises(SystemExit):
            zoomies.main(["run"])  # missing --config, but parsing never touched status
        self.assertNotIn("status", sys.modules)


if __name__ == "__main__":
    unittest.main()
