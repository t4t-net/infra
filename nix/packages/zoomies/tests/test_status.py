"""zoomies status: state derivation, sorting nd th --once table, all against a fake fleet"""
import io
import json
import sys
import threading
import time
import unittest
from pathlib import Path

# discover -s tests puts tests/ on th path, not th package dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import status  # noqa: E402

NOW = 1795700600
PATH_A = "/nix/store/aaaaaaaabbbbbbbbccccccccdddddddd-nixos-system-iris-26.05"
PATH_B = "/nix/store/zzzzzzzzyyyyyyyyxxxxxxxxwwwwwwww-nixos-system-iris-26.05"
KERNEL_1 = "/nix/store/kkkkkkkk-linux-6.12.1"
KERNEL_2 = "/nix/store/llllllll-linux-6.12.2"


def latest(run, path, finished_at=NOW - 300):
    return json.dumps({"run": run, "rev": "f" * 40, "job": "nixos.x", "path": path,
                       "finished_at": finished_at}).encode()


def metrics_out(current, result="success", booted=KERNEL_1, kernel=KERNEL_1, active="inactive",
                exit_ts=NOW - 60, source="zoomies"):
    """a /metrics page like node_exporter serves it, w hydra-deploy's textfile in it"""
    return (
        "# HELP node_load1 1m load average.\nnode_load1 0.5\n"
        f'hydra_deploy_info{{source="{source}",current="{current}",applied="{current}"}} 1\n'
        f"hydra_deploy_last_tick_success {1 if result == 'success' else 0}\n"
        f"hydra_deploy_last_tick_timestamp_seconds {exit_ts}\n"
        f"hydra_deploy_reboot_pending {1 if booted != kernel else 0}\n"
        f"hydra_deploy_switching {1 if active == 'activating' else 0}\n"
    )


class Fleet:
    """fake fetch + metrics probe keyed by host. a value tht's an exception gets raised"""

    def __init__(self, published, running):
        self.published, self.running = published, running

    def fetch(self, url):
        host = url.rsplit("/latest/nixos.", 1)[1][: -len(".json")]
        v = self.published.get(host)
        if isinstance(v, Exception):
            raise v
        return v

    def probe(self, host):
        v = self.running[host]
        if isinstance(v, Exception):
            raise v
        if callable(v):
            return v()
        return v


def gather(fleet, hosts=None, timeout=5):
    hosts = hosts or sorted(fleet.running)
    return {s["host"]: s for s in status.gather(hosts, "http://z", fleet.fetch, fleet.probe,
                                                timeout=timeout)}


class TestState(unittest.TestCase):
    def test_in_sync_behind_never_published(self):
        fleet = Fleet(
            {"iris": latest(213, PATH_A), "pawpatch": latest(213, PATH_A), "peer2peer": None},
            {"iris": metrics_out(PATH_A), "pawpatch": metrics_out(PATH_B), "peer2peer": metrics_out(PATH_A)},
        )
        got = gather(fleet)
        self.assertEqual(got["iris"]["state"], "in-sync")
        self.assertEqual(got["pawpatch"]["state"], "behind")
        self.assertEqual(got["peer2peer"]["state"], "never-published")

    def test_agent_exit_code_is_agent_failed(self):
        fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": metrics_out(PATH_A, result="exit-code")})
        self.assertEqual(gather(fleet)["iris"]["state"], "agent-failed")

    def test_probe_error_is_unreachable(self):
        fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": RuntimeError("Connection refused")})
        st = gather(fleet)["iris"]
        self.assertEqual(st["state"], "unreachable")
        self.assertIn("Connection refused", st["probe_error"])

    def test_hung_probe_is_unreachable_nd_doesnt_block_others(self):
        release = threading.Event()
        fleet = Fleet(
            {"iris": latest(1, PATH_A), "pawpatch": latest(1, PATH_A)},
            {"iris": lambda: (release.wait(10), metrics_out(PATH_A))[1], "pawpatch": metrics_out(PATH_A)},
        )
        try:
            t0 = time.monotonic()
            got = gather(fleet, timeout=0.3)
            self.assertLess(time.monotonic() - t0, 2)
        finally:
            release.set()
        self.assertEqual(got["iris"]["state"], "unreachable")
        self.assertEqual(got["iris"]["probe_error"], "timed out")
        self.assertEqual(got["pawpatch"]["state"], "in-sync")

    def test_reboot_pending(self):
        fleet = Fleet(
            {"iris": latest(1, PATH_A), "pawpatch": latest(1, PATH_A)},
            {"iris": metrics_out(PATH_A, booted=KERNEL_1, kernel=KERNEL_2), "pawpatch": metrics_out(PATH_A)},
        )
        got = gather(fleet)
        self.assertTrue(got["iris"]["running"]["reboot_pending"])
        self.assertFalse(got["pawpatch"]["running"]["reboot_pending"])
        self.assertIn("REBOOT", status.format_row(got["iris"], NOW))
        self.assertEqual(got["iris"]["state"], "in-sync")

    def test_sort_order(self):
        fleet = Fleet(
            {h: latest(5, PATH_A) for h in ["a-sync", "b-behind", "c-failed", "d-down", "e-sync"]},
            {"a-sync": metrics_out(PATH_A), "e-sync": metrics_out(PATH_A), "b-behind": metrics_out(PATH_B),
             "c-failed": metrics_out(PATH_A, result="exit-code"), "d-down": OSError("no route")},
        )
        hosts = ["e-sync", "a-sync", "b-behind", "c-failed", "d-down"]
        order = [s["host"] for s in status.gather(hosts, "http://z", fleet.fetch, fleet.probe)]
        self.assertEqual(order, ["d-down", "c-failed", "b-behind", "a-sync", "e-sync"])


class TestDefensive(unittest.TestCase):
    def test_malformed_json(self):
        for raw in [b"{not json", b"[]", b'{"run": 1}', b"\xff\xfe"]:
            fleet = Fleet({"iris": raw}, {"iris": metrics_out(PATH_A)})
            st = gather(fleet)["iris"]
            self.assertEqual(st["state"], "fetch-error", raw)
            self.assertIsNone(st["published"])
            status.format_row(st, NOW)

    def test_fetch_exception(self):
        fleet = Fleet({"iris": OSError("tailnet down")}, {"iris": metrics_out(PATH_A)})
        st = gather(fleet)["iris"]
        self.assertEqual(st["state"], "fetch-error")
        self.assertIn("err: tailnet down", status.format_row(st, NOW)[2])

    def test_metrics_without_agent_is_no_agent(self):
        for out in ["", "garbage\n", "node_load1 0.5\n", "hydra_deploy_last_tick_success 1\n"]:
            fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": out})
            st = gather(fleet)["iris"]
            self.assertEqual(st["state"], "no-agent", out)
            row = status.format_row(st, NOW)
            self.assertEqual(row[0], "iris", out)
            self.assertEqual(row[4], "no agent", out)

    def test_partial_metrics(self):
        info = f'hydra_deploy_info{{source="zoomies",current="{PATH_A}",applied=""}} 1\n'
        for out in [info, info + "hydra_deploy_last_tick_success nope\n",
                    info + "hydra_deploy_reboot_pending\n", info + "hydra_deploy_bogus 1 2 3\n"]:
            fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": out})
            st = gather(fleet)["iris"]
            self.assertEqual(st["state"], "in-sync", out)
            self.assertFalse(st["running"]["reboot_pending"], out)
            self.assertIsNone(st["running"]["result"], out)
            status.format_row(st, NOW)

    def test_metrics_probe_hits_port_9100(self):
        seen = []
        real = status.http_fetch
        try:
            status.http_fetch = lambda url, timeout=10: (seen.append(url), b"x")[1]
            self.assertEqual(status.metrics_probe("100.123.106.62"), "x")
        finally:
            status.http_fetch = real
        self.assertEqual(seen, ["http://100.123.106.62:9100/metrics"])

    def test_wrong_types_in_json(self):
        raw = json.dumps({"run": "213", "path": PATH_A, "finished_at": "soon"}).encode()
        fleet = Fleet({"iris": raw}, {"iris": metrics_out(PATH_A)})
        st = gather(fleet)["iris"]
        self.assertEqual(st["state"], "in-sync")
        row = status.format_row(st, NOW)
        self.assertEqual(row[2], "r? aaaaaaaa")
        self.assertEqual(row[6], "-")


class TestFormatting(unittest.TestCase):
    def test_store_hash_nd_age(self):
        self.assertEqual(status.store_hash(PATH_A), "aaaaaaaa")
        self.assertEqual(status.store_hash(None), "-")
        self.assertEqual(status.fmt_age(45), "45s")
        self.assertEqual(status.fmt_age(300), "5m")
        self.assertEqual(status.fmt_age(7200), "2h")
        self.assertEqual(status.fmt_age(3 * 86400), "3d")

    def test_deploying_shows_instead_of_result(self):
        fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": metrics_out(PATH_B, active="activating")})
        self.assertEqual(status.format_row(gather(fleet)["iris"], NOW)[4], "deploying")

    def test_once_output(self):
        fleet = Fleet(
            {"iris": latest(213, PATH_A), "pawpatch": latest(212, PATH_A), "ghostholding": None},
            {"iris": metrics_out(PATH_A), "pawpatch": metrics_out(PATH_B, result="exit-code"),
             "ghostholding": TimeoutError("timed out")},
        )
        buf = io.StringIO()
        rc = status.main(["--once", "--url", "http://z", "--hosts", "iris,pawpatch,ghostholding"],
                         fetch=fleet.fetch, probe=fleet.probe, now=lambda: NOW, out=buf)
        self.assertEqual(rc, 0)
        lines = buf.getvalue().splitlines()
        self.assertIn("zoomies http://z", lines[0])
        self.assertIn("newest run r213", lines[0])
        self.assertEqual(lines[2].split(), status.COLUMNS)
        body = [line.split() for line in lines[3:]]
        self.assertEqual([r[0] for r in body], ["!ghostholding", "!pawpatch", "iris"])
        self.assertEqual(body[0][1], "unreachable")
        self.assertEqual(body[1][1:5], ["agent-failed", "r212", "aaaaaaaa", "zzzzzzzz"])
        self.assertEqual(body[2], ["iris", "in-sync", "r213", "aaaaaaaa", "aaaaaaaa",
                                   "success", "1m", "5m"])

    def test_not_a_tty_falls_back_2_once(self):
        fleet = Fleet({"iris": None}, {"iris": metrics_out(PATH_A)})
        buf = io.StringIO()
        rc = status.main(["--hosts", "iris"], fetch=fleet.fetch, probe=fleet.probe,
                         now=lambda: NOW, out=buf)
        self.assertEqual(rc, 0)
        self.assertIn("never-published", buf.getvalue())

    def test_default_hosts(self):
        args = status.parse_args([])
        self.assertEqual(args.hosts.split(","), status.DEFAULT_HOSTS)
        self.assertEqual(args.url, "https://zoomies.tail09d5b.ts.net")


class TestHostAddress(unittest.TestCase):
    def test_parse_host(self):
        self.assertEqual(status.parse_host("iris"), ("iris", "iris"))
        self.assertEqual(status.parse_host("experimental-skin=100.123.106.62"),
                         ("experimental-skin", "100.123.106.62"))
        self.assertEqual(status.parse_host(" iris = 100.1.2.3 "), ("iris", "100.1.2.3"))
        self.assertEqual(status.parse_host("iris="), ("iris", "iris"))

    def test_default_hosts_pin_experimental_skin_v4(self):
        self.assertIn("experimental-skin=100.123.106.62", status.DEFAULT_HOSTS)

    def test_probe_gets_address_fetch_gets_name(self):
        fetched, probed = [], []

        def fetch(url):
            fetched.append(url)
            return latest(7, PATH_A)

        def probe(addr):
            probed.append(addr)
            return metrics_out(PATH_A)

        got = status.gather(["experimental-skin=100.123.106.62", "iris"], "http://z", fetch, probe)
        self.assertEqual(sorted(probed), ["100.123.106.62", "iris"])
        self.assertEqual(sorted(fetched), ["http://z/latest/nixos.experimental-skin.json",
                                           "http://z/latest/nixos.iris.json"])
        self.assertEqual([s["host"] for s in got], ["experimental-skin", "iris"])
        self.assertTrue(all(s["state"] == "in-sync" for s in got))

    def test_once_shows_name_not_address(self):
        buf = io.StringIO()
        status.main(["--once", "--url", "http://z", "--hosts", "experimental-skin=100.123.106.62"],
                    fetch=lambda u: latest(7, PATH_A), probe=lambda a: metrics_out(PATH_A),
                    now=lambda: NOW, out=buf)
        self.assertIn("experimental-skin", buf.getvalue())
        self.assertNotIn("100.123.106.62", buf.getvalue())

    def test_timed_out_row_uses_name(self):
        release = threading.Event()
        try:
            got = status.gather(["experimental-skin=100.123.106.62"], "http://z",
                                lambda u: None, lambda a: (release.wait(10), "")[1], timeout=0.2)
        finally:
            release.set()
        self.assertEqual(got[0]["host"], "experimental-skin")
        self.assertEqual(got[0]["state"], "unreachable")


if __name__ == "__main__":
    unittest.main()
