"""shared by th tests: where th code is, th frozen fixture, nd th time it's frozen at"""
import gzip
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

NOW = 1794452208 + 60  # just after th fixture's last watch poll, so th live tail counts (its last api dump is 1794450101)


def fixture_db(tmp):
    """unpack th fixture into tmp nd return its path"""
    db = Path(tmp) / "fixture.sqlite"
    with gzip.open(HERE / "fixture.sqlite.gz") as g, open(db, "wb") as f:
        shutil.copyfileobj(g, f)
    return db
