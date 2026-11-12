"""th addon's full dumps price th site when they're newer than th api's, nd watch polls still win when newer"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import NOW, fixture_db

import forever_ah  # noqa: E402

PEACEBLOOM = 2447   # api only in th fixture
LINEN = 2589        # watched, last poll at 1794451749
LAST_POLL = 1794451749


def export(scan_t, timed_out=False):
    """export th fixture w one addon dump at scan_t pricing peacebloom at 11c nd linen at 12c"""
    with tempfile.TemporaryDirectory() as tmp:
        path = fixture_db(tmp)
        db = sqlite3.connect(path)
        sid = db.execute(
            "insert into addon_scan (server_ts, character, house_id, listings, forced, timed_out) "
            "values (?, 'test', 111, 2, 0, ?)", (scan_t, int(timed_out))).lastrowid
        db.executemany("insert into addon_price values (?, ?, 1, ?, ?, 20, 1)",
                       [(sid, PEACEBLOOM, 11, 11), (sid, LINEN, 12, 12)])
        db.commit()
        db.close()
        out = Path(tmp) / "www" / "data.json"
        argv = ["forever-ah", "--db", str(path), "export", "--now", str(NOW), "--out", str(out)]
        with mock.patch.object(sys, "argv", argv):
            forever_ah.main()
        data = json.loads(out.read_text())
    rows = {m["id"]: m for ms in data["gather"].values() for m in ms}
    return data, rows


class AddonDump(unittest.TestCase):
    def test_newest_dump_takes_over(self):
        data, rows = export(NOW - 30)
        self.assertEqual(data["addon_dump"], NOW - 30)
        for i, floor in ((PEACEBLOOM, 11), (LINEN, 12)):
            self.assertEqual((rows[i]["floor"], rows[i]["source"], rows[i]["as_of"]), (floor, "addon", NOW - 30))

    def test_newer_watch_poll_beats_an_older_dump(self):
        data, rows = export(LAST_POLL - 600)
        self.assertEqual(rows[PEACEBLOOM]["source"], "addon")
        self.assertEqual((rows[LINEN]["source"], rows[LINEN]["as_of"]), ("watch", LAST_POLL))

    def test_broken_dump_is_ignored(self):
        data, rows = export(NOW - 30, timed_out=True)
        self.assertIsNone(data["addon_dump"])
        self.assertEqual(rows[PEACEBLOOM]["source"], "api")


if __name__ == "__main__":
    unittest.main()
