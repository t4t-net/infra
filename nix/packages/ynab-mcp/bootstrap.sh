#!/usr/bin/env bash
# one-time: get a read-only ynab grant nd hand its refresh token 2 ynab-mcp on iris. runs on ellie's
# laptop, cuz th client secret comes out of sops nd th consent page needs a browser
set -euo pipefail

secrets="${1:-$(dirname "$0")/../../machines/nixos/iris/secrets/ynab-mcp.yaml}"
host="${YNAB_MCP_HOST:-iris.sfo.t4t.net}"
redirect="${YNAB_REDIRECT_URI:-urn:ietf:wg:oauth:2.0:oob}"

client_id="$(sops -d --extract '["client_id"]' "$secrets")"
client_secret="$(sops -d --extract '["client_secret"]' "$secrets")"
state="$(openssl rand -hex 16)"

uri() { jq -rn --arg v "$1" '$v|@uri'; }
echo "open this nd approve:"
echo "https://app.ynab.com/oauth/authorize?client_id=$(uri "$client_id")&redirect_uri=$(uri "$redirect")&response_type=code&scope=read-only&state=$state"
echo
read -rp "paste th code, or th whole url u got redirected 2: " reply

code="$reply"
if [[ "$reply" == *"code="* ]]; then
  code="$(sed -n 's/.*[?&]code=\([^&]*\).*/\1/p' <<<"$reply")"
  got_state="$(sed -n 's/.*[?&]state=\([^&]*\).*/\1/p' <<<"$reply")"
  # a bare code or an oob page url has no state 2 check, thats fine 4 a flow u started urself
  if [[ -n "$got_state" && "$got_state" != "$state" ]]; then
    echo "state mismatch, not using this code" >&2
    exit 1
  fi
fi

# th secret goes thru a pipe, on th command line it would show up in ps. --fail-with-body so a
# redirect_uri mismatch or invalid_grant actually says so
resp="$(curl -sS --fail-with-body https://app.ynab.com/oauth/token \
  --data-urlencode "client_id=$client_id" \
  --data-urlencode "client_secret@"<(printf '%s' "$client_secret") \
  --data-urlencode "redirect_uri=$redirect" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=$code")"

scope="$(jq -r '.scope // "unset"' <<<"$resp")"
if [[ "$scope" != "read-only" && "$scope" != "unset" ]]; then
  echo "grant came back w scope '$scope', not handing it over" >&2
  exit 1
fi
echo "scope: $scope"

refresh="$(jq -r '.refresh_token // empty' <<<"$resp")"
if [[ -z "$refresh" ]]; then
  echo "no refresh_token in th response, not handing anything over" >&2
  exit 1
fi

# th unit has 2 have started once so its state dir exists. a restart does NOT chown th file, systemd
# skips th whole tree wen th dir's owner is already right, so th file gets th dir's owner here
printf '%s' "$refresh" | ssh "root@$host" \
  'd=/var/lib/private/ynab-mcp && install -m600 -o "$(stat -c %u $d)" -g "$(stat -c %g $d)" /dev/stdin $d/refresh-token && systemctl restart ynab-mcp'
echo "done!! ynab-mcp on $host has its refresh token"
