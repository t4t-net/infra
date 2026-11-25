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


def ssh_out(current, result="success", booted=KERNEL_1, kernel=KERNEL_1, active="inactive",
            exit_ts=NOW - 60):
    return (f"current={current}\nbooted_kernel={booted}\ncurrent_kernel={kernel}\n"
            f"Result={result}\nExecMainExitTimestamp=@{exit_ts}\nActiveState={active}\n")


class Fleet:
    """fake fetch + ssh keyed by host. a value tht's an exception gets raised"""

    def __init__(self, published, running):
        self.published, self.running = published, running

    def fetch(self, url):
        host = url.rsplit("/latest/nixos.", 1)[1][: -len(".json")]
        v = self.published.get(host)
        if isinstance(v, Exception):
            raise v
        return v

    def ssh(self, host):
        v = self.running[host]
        if isinstance(v, Exception):
            raise v
        if callable(v):
            return v()
        return v


def gather(fleet, hosts=None, timeout=5):
    hosts = hosts or sorted(fleet.running)
    return {s["host"]: s for s in status.gather(hosts, "http://z", fleet.fetch, fleet.ssh,
                                                timeout=timeout)}


class TestState(unittest.TestCase):
    def test_in_sync_behind_never_published(self):
        fleet = Fleet(
            {"iris": latest(213, PATH_A), "pawpatch": latest(213, PATH_A), "peer2peer": None},
            {"iris": ssh_out(PATH_A), "pawpatch": ssh_out(PATH_B), "peer2peer": ssh_out(PATH_A)},
        )
        got = gather(fleet)
        self.assertEqual(got["iris"]["state"], "in-sync")
        self.assertEqual(got["pawpatch"]["state"], "behind")
        self.assertEqual(got["peer2peer"]["state"], "never-published")

    def test_agent_exit_code_is_agent_failed(self):
        fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": ssh_out(PATH_A, result="exit-code")})
        self.assertEqual(gather(fleet)["iris"]["state"], "agent-failed")

    def test_ssh_error_is_unreachable(self):
        fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": RuntimeError("Connection refused")})
        st = gather(fleet)["iris"]
        self.assertEqual(st["state"], "unreachable")
        self.assertIn("Connection refused", st["ssh_error"])

    def test_hung_ssh_is_unreachable_nd_doesnt_block_others(self):
        release = threading.Event()
        fleet = Fleet(
            {"iris": latest(1, PATH_A), "pawpatch": latest(1, PATH_A)},
            {"iris": lambda: (release.wait(10), ssh_out(PATH_A))[1], "pawpatch": ssh_out(PATH_A)},
        )
        try:
            t0 = time.monotonic()
            got = gather(fleet, timeout=0.3)
            self.assertLess(time.monotonic() - t0, 2)
        finally:
            release.set()
        self.assertEqual(got["iris"]["state"], "unreachable")
        self.assertEqual(got["iris"]["ssh_error"], "timed out")
        self.assertEqual(got["pawpatch"]["state"], "in-sync")

    def test_reboot_pending(self):
        fleet = Fleet(
            {"iris": latest(1, PATH_A), "pawpatch": latest(1, PATH_A)},
            {"iris": ssh_out(PATH_A, booted=KERNEL_1, kernel=KERNEL_2), "pawpatch": ssh_out(PATH_A)},
        )
        got = gather(fleet)
        self.assertTrue(got["iris"]["running"]["reboot_pending"])
        self.assertFalse(got["pawpatch"]["running"]["reboot_pending"])
        self.assertIn("REBOOT", status.format_row(got["iris"], NOW))
        self.assertEqual(got["iris"]["state"], "in-sync")

    def test_sort_order(self):
        fleet = Fleet(
            {h: latest(5, PATH_A) for h in ["a-sync", "b-behind", "c-failed", "d-down", "e-sync"]},
            {"a-sync": ssh_out(PATH_A), "e-sync": ssh_out(PATH_A), "b-behind": ssh_out(PATH_B),
             "c-failed": ssh_out(PATH_A, result="exit-code"), "d-down": OSError("no route")},
        )
        hosts = ["e-sync", "a-sync", "b-behind", "c-failed", "d-down"]
        order = [s["host"] for s in status.gather(hosts, "http://z", fleet.fetch, fleet.ssh)]
        self.assertEqual(order, ["d-down", "c-failed", "b-behind", "a-sync", "e-sync"])


class TestDefensive(unittest.TestCase):
    def test_malformed_json(self):
        for raw in [b"{not json", b"[]", b'{"run": 1}', b"\xff\xfe"]:
            fleet = Fleet({"iris": raw}, {"iris": ssh_out(PATH_A)})
            st = gather(fleet)["iris"]
            self.assertEqual(st["state"], "fetch-error", raw)
            self.assertIsNone(st["published"])
            status.format_row(st, NOW)

    def test_fetch_exception(self):
        fleet = Fleet({"iris": OSError("tailnet down")}, {"iris": ssh_out(PATH_A)})
        st = gather(fleet)["iris"]
        self.assertEqual(st["state"], "fetch-error")
        self.assertIn("err: tailnet down", status.format_row(st, NOW)[2])

    def test_partial_ssh_output(self):
        for out in ["", "garbage\n", f"current={PATH_A}\n", "current=\nResult=\n",
                    "booted_kernel=x\nExecMainExitTimestamp=n/a\n"]:
            fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": out})
            st = gather(fleet)["iris"]
            self.assertIn(st["state"], ("in-sync", "behind"), out)
            self.assertFalse(st["running"]["reboot_pending"], out)
            status.format_row(st, NOW)

    def test_wrong_types_in_json(self):
        raw = json.dumps({"run": "213", "path": PATH_A, "finished_at": "soon"}).encode()
        fleet = Fleet({"iris": raw}, {"iris": ssh_out(PATH_A)})
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
        fleet = Fleet({"iris": latest(1, PATH_A)}, {"iris": ssh_out(PATH_B, active="activating")})
        self.assertEqual(status.format_row(gather(fleet)["iris"], NOW)[4], "deploying")

    def test_once_output(self):
        fleet = Fleet(
            {"iris": latest(213, PATH_A), "pawpatch": latest(212, PATH_A), "ghostholding": None},
            {"iris": ssh_out(PATH_A), "pawpatch": ssh_out(PATH_B, result="exit-code"),
             "ghostholding": TimeoutError("timed out")},
        )
        buf = io.StringIO()
        rc = status.main(["--once", "--url", "http://z", "--hosts", "iris,pawpatch,ghostholding"],
                         fetch=fleet.fetch, ssh=fleet.ssh, now=lambda: NOW, out=buf)
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
        fleet = Fleet({"iris": None}, {"iris": ssh_out(PATH_A)})
        buf = io.StringIO()
        rc = status.main(["--hosts", "iris"], fetch=fleet.fetch, ssh=fleet.ssh,
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

    def test_ssh_gets_address_fetch_gets_name(self):
        fetched, sshed = [], []

        def fetch(url):
            fetched.append(url)
            return latest(7, PATH_A)

        def ssh(addr):
            sshed.append(addr)
            return ssh_out(PATH_A)

        got = status.gather(["experimental-skin=100.123.106.62", "iris"], "http://z", fetch, ssh)
        self.assertEqual(sorted(sshed), ["100.123.106.62", "iris"])
        self.assertEqual(sorted(fetched), ["http://z/latest/nixos.experimental-skin.json",
                                           "http://z/latest/nixos.iris.json"])
        self.assertEqual([s["host"] for s in got], ["experimental-skin", "iris"])
        self.assertTrue(all(s["state"] == "in-sync" for s in got))

    def test_once_shows_name_not_address(self):
        buf = io.StringIO()
        status.main(["--once", "--url", "http://z", "--hosts", "experimental-skin=100.123.106.62"],
                    fetch=lambda u: latest(7, PATH_A), ssh=lambda a: ssh_out(PATH_A),
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
