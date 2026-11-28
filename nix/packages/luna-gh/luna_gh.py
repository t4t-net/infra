#!/usr/bin/env python3
"""luna-gh: be th luna-t4t github app, so luna's PRs r hers nd ellie gets 2 approve them.

th app key lives in 1password as a document (concealed fields mangle th PEM's newlines). every
call reads it w `op document get`, signs a 10 min app JWT w openssl, nd trades it 4 a 1h
installation token. th key reaches openssl thru a pipe fd nd th token goes straight 2 git or gh,
so neither ever touches disk or luna's stdout. no cache on purpose: 1p's own session already
saves touch id prompts, nd a cached token is just a plaintext secret w extra steps.

  luna-gh credential get   git credential helper (`!luna-gh credential` in th repo's git config)
  luna-gh gh ARGS...       exec gh as th app (GH_TOKEN only lives in gh's env)
  luna-gh check            print installation id, expiry nd permissions. never th token
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

API = "https://api.github.com"


@dataclass(frozen=True)
class Config:
    app_id: str
    org: str
    key_doc: str
    openssl: str
    op: str

    @classmethod
    def from_env(cls, env):
        return cls(
            app_id=env.get("LUNA_GH_APP_ID", "5958174"),
            org=env.get("LUNA_GH_ORG", "t4t-net"),
            key_doc=env.get("LUNA_GH_KEY_DOC", "luna-github-app-private-key"),
            # package.nix pins this 2 nixpkgs openssl
            openssl=env.get("LUNA_GH_OPENSSL", "openssl"),
            # from PATH, so it's th op tht talks 2 ellie's 1p desktop app (touch id)
            op=env.get("LUNA_GH_OP", "op"),
        )


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def sign_jwt(app_id, key_pem, now, openssl):
    """RS256 app JWT. iat is backdated a minute 4 clock skew, github caps exp at 10 min"""
    head = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    body = b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}).encode())
    signing_input = head + b"." + body
    # a PEM is a few KB, way under th pipe buffer, so writing it all b4 openssl reads cant block
    r, w = os.pipe()
    try:
        os.write(w, key_pem)
        os.close(w)
        sig = subprocess.run(
            [openssl, "dgst", "-sha256", "-sign", f"/dev/fd/{r}"],
            input=signing_input,
            capture_output=True,
            check=True,
            pass_fds=(r,),
        ).stdout
    finally:
        os.close(r)
    return (signing_input + b"." + b64url(sig)).decode()


def api(method, path, bearer, opener=urllib.request.urlopen):
    req = urllib.request.Request(
        API + path,
        method=method,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "luna-gh",
        },
    )
    with opener(req) as resp:
        return json.load(resp)


def read_key(cfg):
    return subprocess.run(
        [cfg.op, "document", "get", cfg.key_doc], capture_output=True, check=True
    ).stdout


def installation_token(cfg, read_key=read_key, api=api, now=time.time):
    """{"token", "expires_at", "permissions", ...} 4 th app's install on cfg.org"""
    jwt = sign_jwt(cfg.app_id, read_key(cfg), int(now()), cfg.openssl)
    inst = api("GET", f"/orgs/{cfg.org}/installation", jwt)
    tok = api("POST", f"/app/installations/{inst['id']}/access_tokens", jwt)
    tok["installation_id"] = inst["id"]
    return tok


def credential(action, stdin_text, get_token):
    """git credential protocol. only answers `get` 4 https://github.com, everything else is a no-op"""
    if action != "get":
        return ""
    attrs = dict(line.split("=", 1) for line in stdin_text.splitlines() if "=" in line)
    if attrs.get("protocol") != "https" or attrs.get("host") != "github.com":
        return ""
    return f"username=x-access-token\npassword={get_token()}\n"


def main(argv, env, stdin, stdout):
    p = argparse.ArgumentParser(prog="luna-gh", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("credential", help="git credential helper")
    c.add_argument("action", choices=["get", "store", "erase"])
    g = sub.add_parser("gh", help="run gh as th app")
    g.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("check", help="mint a token nd print everything but th token")
    args = p.parse_args(argv)
    cfg = Config.from_env(env)

    try:
        if args.cmd == "credential":
            text = stdin.read()
            stdout.write(credential(args.action, text, lambda: installation_token(cfg)["token"]))
        elif args.cmd == "gh":
            tok = installation_token(cfg)["token"]
            os.execvpe("gh", ["gh", *args.args], {**env, "GH_TOKEN": tok})
        elif args.cmd == "check":
            tok = installation_token(cfg)
            print(f"installation {tok['installation_id']} on {cfg.org} (app {cfg.app_id})", file=stdout)
            print(f"expires_at   {tok['expires_at']}", file=stdout)
            print(f"repos        {tok.get('repository_selection', '?')}", file=stdout)
            print(f"permissions  {json.dumps(tok['permissions'], sort_keys=True)}", file=stdout)
    except subprocess.CalledProcessError as e:
        # stderr from op/openssl, never th key itself
        print(f"luna-gh: {e.cmd[0]} failed: {e.stderr.decode(errors='replace').strip()}", file=sys.stderr)
        return 1
    except urllib.error.HTTPError as e:
        print(f"luna-gh: github said {e.code} 4 {e.url}: {e.read()[:300].decode(errors='replace')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ), sys.stdin, sys.stdout))
