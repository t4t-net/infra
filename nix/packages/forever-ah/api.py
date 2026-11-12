"""battle.net api client, throttled nd 429-aware, plus where th creds live."""
import base64
import email.utils
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Client:
    """Blizzard API client, throttled 2 half th 100 req/s limit. th 36k req/h cap is wat bites first:
    a full recipe crawl is ~4k calls, so only back-2-back giant crawls get near it (429s back off)."""

    def __init__(self, region, client_id, client_secret, min_interval=0.02, retries=5):
        self.region = region
        self.min_interval = min_interval
        self.retries = retries
        self.last = 0.0
        self.lock = threading.Lock()
        # of th most recent response, as unix seconds. only meaningful 4 sequential get()s, not get_many
        self.last_modified = None
        req = urllib.request.Request(
            "https://oauth.battle.net/token",
            data=b"grant_type=client_credentials",
            headers={"Authorization": "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            self.token = json.load(r)["access_token"]

    def get(self, path, namespace="dynamic"):
        """GET path in {namespace}-forever-{region}; returns None on 404."""
        url = f"https://{self.region}.api.blizzard.com{path}?" + urllib.parse.urlencode(
            {"namespace": f"{namespace}-forever-{self.region}", "locale": "en_US"}
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        for attempt in range(self.retries):
            # reserve th next free slot under th lock, then sleep outside it so other threads queue up behind
            with self.lock:
                now = time.monotonic()
                slot = max(now, self.last + self.min_interval)
                self.last = slot
            if slot > now:
                time.sleep(slot - now)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    lm = r.headers.get("Last-Modified")
                    self.last_modified = int(email.utils.parsedate_to_datetime(lm).timestamp()) if lm else None
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code != 429 and e.code < 500:
                    raise
                time.sleep(int(e.headers.get("Retry-After") or 2 ** attempt))
        raise RuntimeError(f"gave up on {path} after {self.retries} attempts")

    def get_many(self, paths, namespace="dynamic", workers=16):
        """get() each path concurrently, results in th same order. one request at a time is latency-bound
        at ~7/s from psychoboost, so th throttle only actually matters once there r a bunch in flight"""
        with ThreadPoolExecutor(workers) as pool:
            return list(pool.map(lambda p: self.get(p, namespace), paths))


def creds():
    if "BNET_CLIENT_ID" in os.environ:
        return os.environ["BNET_CLIENT_ID"], os.environ["BNET_CLIENT_SECRET"]
    secrets = Path("~/.secrets").expanduser()
    return (
        (secrets / "battle-net-client-id").read_text().strip(),
        (secrets / "battle-net-client-secret").read_text().strip(),
    )
