import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import luna_gh  # noqa: E402

OPENSSL = os.environ.get("LUNA_GH_OPENSSL", "openssl")


def unb64(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class JwtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # a throwaway key just 4 th test, never leaves th tempdir
        cls.dir = tempfile.TemporaryDirectory()
        d = Path(cls.dir.name)
        subprocess.run([OPENSSL, "genrsa", "-out", d / "k.pem", "2048"], check=True, capture_output=True)
        subprocess.run([OPENSSL, "rsa", "-in", d / "k.pem", "-pubout", "-out", d / "pub.pem"], check=True, capture_output=True)
        cls.key = (d / "k.pem").read_bytes()
        cls.pub = d / "pub.pem"

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_claims_and_signature_verify(self):
        jwt = luna_gh.sign_jwt("5958174", self.key, 1_000_000, OPENSSL)
        head, body, sig = jwt.split(".")
        self.assertEqual(json.loads(unb64(head)), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(json.loads(unb64(body)), {"iat": 999_940, "exp": 1_000_540, "iss": "5958174"})
        with tempfile.NamedTemporaryFile() as s:
            s.write(unb64(sig))
            s.flush()
            ok = subprocess.run(
                [OPENSSL, "dgst", "-sha256", "-verify", self.pub, "-signature", s.name],
                input=f"{head}.{body}".encode(),
                capture_output=True,
            )
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_installation_token_flow(self):
        calls = []

        def fake_api(method, path, bearer):
            calls.append((method, path))
            if path == "/orgs/t4t-net/installation":
                return {"id": 42}
            return {"token": "tok", "expires_at": "later", "permissions": {}}

        cfg = luna_gh.Config.from_env({"LUNA_GH_OPENSSL": OPENSSL})
        tok = luna_gh.installation_token(cfg, read_key=lambda _: self.key, api=fake_api, now=lambda: 1_000_000)
        self.assertEqual(tok["token"], "tok")
        self.assertEqual(tok["installation_id"], 42)
        self.assertEqual(calls, [("GET", "/orgs/t4t-net/installation"), ("POST", "/app/installations/42/access_tokens")])


class CredentialTest(unittest.TestCase):
    def boom(self):
        raise AssertionError("minted a token it shouldnt have")

    def test_github_https_get(self):
        out = luna_gh.credential("get", "protocol=https\nhost=github.com\npath=t4t-net/infra.git\n", lambda: "tok")
        self.assertEqual(out, "username=x-access-token\npassword=tok\n")

    def test_other_hosts_and_protocols_are_ignored(self):
        self.assertEqual(luna_gh.credential("get", "protocol=https\nhost=gitlab.com\n", self.boom), "")
        self.assertEqual(luna_gh.credential("get", "protocol=http\nhost=github.com\n", self.boom), "")

    def test_store_and_erase_are_noops(self):
        for action in ("store", "erase"):
            self.assertEqual(luna_gh.credential(action, "protocol=https\nhost=github.com\npassword=x\n", self.boom), "")


if __name__ == "__main__":
    unittest.main()
