"""Snapshot test: `forever-ah export` on th frozen fixture must keep producing tests/golden/*.json.

  python3 -m unittest discover -s tests                     run it
  UPDATE_GOLDEN=1 python3 -m unittest discover -s tests     accept th current output as golden

th refactor's safety net: splitting th code shudnt change a single number. when a change is MEANT 2
change numbers, regenerate th golden nd th jj diff of tests/golden is th review
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import HERE, NOW, fixture_db

import api  # noqa: E402
import forever_ah  # noqa: E402


def diffs(a, b, path="$"):
    """paths where a nd b differ, so a failure says wat moved instead of dumping two huge dicts"""
    if type(a) is not type(b):
        yield f"{path}: {a!r} -> {b!r}"
    elif isinstance(a, dict):
        for k in sorted(a.keys() | b.keys(), key=str):
            if k not in a or k not in b:
                yield f"{path}.{k}: {'missing' if k not in a else a[k]!r} -> {'missing' if k not in b else b[k]!r}"
            else:
                yield from diffs(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            yield f"{path}: {len(a)} items -> {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diffs(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {a!r} -> {b!r}"


class Snapshot(unittest.TestCase):
    def test_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fixture_db(tmp)
            out = Path(tmp) / "www" / "data.json"
            argv = ["forever-ah", "--db", str(db), "export", "--now", str(NOW), "--out", str(out)]
            # th fixture carries names nd qualities 4 everything shown, so reaching 4 th api is a bug. patched on
            # th class so it catches every module tht imported Client
            offline = AssertionError("export tried 2 call th api, th fixture is missing a name or quality")
            with mock.patch.object(sys, "argv", argv), mock.patch.object(api.Client, "__init__", side_effect=offline):
                forever_ah.main()

            for name in ("data.json", "quests.json"):
                got = json.loads((out.parent / name).read_text())
                golden = HERE / "golden" / name
                if os.environ.get("UPDATE_GOLDEN"):
                    golden.parent.mkdir(exist_ok=True)
                    golden.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
                    continue
                changed = list(diffs(json.loads(golden.read_text()), got))
                self.assertFalse(changed, f"{name} changed in {len(changed)} places, first few:\n  "
                                 + "\n  ".join(changed[:15]))


if __name__ == "__main__":
    unittest.main()
