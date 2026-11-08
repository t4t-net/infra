#!/usr/bin/env python3
"""read-only ynab mcp server 4 iris.

ynab enforces th read-only scope server side (writes get a 403), so th budget tools r all GETs.
oauth access tokens last 2h, so it refreshes on its own nd saves whatever refresh token comes back,
cuz th docs dont say whether they rotate. wen th grant dies, ellie reconnects it thru iris w
ynab_auth_start/ynab_auth_finish, nd th client secret never leaves this process.
"""

import argparse
import asyncio
import datetime
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

API = "https://api.ynab.com/v1"
TOKEN_URL = "https://app.ynab.com/oauth/token"


class YnabError(Exception):
    pass


class GrantDead(YnabError):
    # th only errors tht a fresh consent fixes, so th only ones ynab_auth_finish will act on
    pass


def oauth_detail(r):
    # oauth errors r just a code + description, no secrets in them
    try:
        body = r.json()
        return body.get("error"), body.get("error_description") or body.get("error")
    except ValueError:
        return None, None


class Tokens:
    def __init__(self, http, client_id, client_secret, refresh_path, redirect_uri):
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_path = refresh_path
        self._redirect_uri = redirect_uri
        self._lock = asyncio.Lock()
        self._access = None
        self._expires = 0.0

    def _save(self, token):
        tmp = self._refresh_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            f.write(token)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._refresh_path)

    def _use(self, body):
        self._access = body["access_token"]
        self._expires = time.monotonic() + body.get("expires_in", 7200) - 300

    def authorize_url(self, state):
        return "https://app.ynab.com/oauth/authorize?" + urlencode({
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": "read-only",
            "state": state,
        })

    async def get(self, force=False):
        async with self._lock:
            if self._access and not force and time.monotonic() < self._expires:
                return self._access
            try:
                refresh = self._refresh_path.read_text().strip()
            except FileNotFoundError:
                raise GrantDead("not connected 2 ynab yet, ellie needs 2 reconnect it (ynab_auth_start)") from None
            except OSError as e:
                raise YnabError(f"cant read th refresh token ({e.strerror}), ellie needs 2 check its owner") from None
            r = await self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                },
            )
            if r.status_code != 200:
                code, detail = oauth_detail(r)
                if code == "invalid_grant":
                    raise GrantDead(f"ynab grant is dead ({detail}), ellie needs 2 reconnect it (ynab_auth_start)")
                raise YnabError(f"token refresh failed: {r.status_code} {detail or ''}")
            body = r.json()
            # saved b4 anything else, if th old one is already dead nd we lose th new one th grant is gone
            new = body.get("refresh_token") or refresh
            if new != refresh:
                self._save(new)
            # ynab already refuses writes, this just stops us running on a grant tht came back wider
            if body.get("scope", "read-only") != "read-only":
                raise YnabError(f"grant has scope {body['scope']!r}, refusing 2 use it")
            self._use(body)
            return self._access

    async def exchange(self, code, check):
        """trade a consent code 4 a grant. check gets th new access token nd raises if th grant
        isnt th one we want, in which case nothing is saved nd th old state stays"""
        async with self._lock:
            r = await self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                    "code": code,
                },
            )
            if r.status_code != 200:
                _, detail = oauth_detail(r)
                raise YnabError(f"code exchange failed: {r.status_code} {detail or ''}")
            body = r.json()
            if body.get("scope", "read-only") != "read-only":
                raise YnabError(f"grant has scope {body['scope']!r}, refusing 2 use it")
            if not body.get("refresh_token"):
                raise YnabError("ynab sent no refresh token, so this grant would die in 2h")
            await check(body["access_token"])
            self._save(body["refresh_token"])
            self._use(body)


class Ynab:
    def __init__(self, http, tokens):
        self._http = http
        self._tokens = tokens

    async def get_with(self, token, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        return await self._http.get(
            f"{API}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
        )

    async def get(self, path, **params):
        # a 401 means th token died early, so one retry w a fresh one
        for force in (False, True):
            r = await self.get_with(await self._tokens.get(force), path, **params)
            if r.status_code != 401:
                break
        if r.status_code >= 400:
            try:
                err = r.json()["error"]
                detail = err.get("detail") or err.get("name")
            except (ValueError, KeyError):
                detail = r.text[:200]
            raise YnabError(f"ynab {r.status_code}: {detail}")
        return r.json()["data"]


def pick(obj, *keys):
    # every amount comes as milliunits, _formatted nd _currency. only th decimal one is worth th context.
    # nulls nd empty debt dicts get dropped 2, they r most of th bytes
    out = {}
    for k in keys:
        v = obj.get(f"{k}_currency", obj.get(k))
        if v is not None and v != {}:
            out[k] = v
    return out


def compact(obj):
    # fastmcp pretty-prints, nd hermes spills anything over 50k chars 2 a file she only sees 1.5k of
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# per ynab's spec: 0/1/2/13 repeat every goal_cadence_frequency of none/month/week/year, 3-12 r
# every 2-11 months nd 14 is every 2 years, both w frequency ignored
UNITS = {1: "month", 2: "week", 13: "year"}


def cadence(c):
    n, freq = c.get("goal_cadence"), c.get("goal_cadence_frequency") or 1
    if n is None:
        return None
    if n == 0:
        return "no repeat"
    if 3 <= n <= 12:
        return f"every {n - 1} months"
    if n == 14:
        return "every 2 years"
    if n in UNITS:
        return f"every {UNITS[n]}" if freq == 1 else f"every {freq} {UNITS[n]}s"
    return f"cadence {n}"


def build_server(ynab, tokens, plan_id, host, port):
    mcp = FastMCP("ynab", host=host, port=port, stateless_http=True)
    plan_id_default = plan_id or "last-used"
    # consent states handed out by ynab_auth_start, state -> expiry
    pending = {}
    # structured output would send every result twice, once as text nd once as structuredContent
    tool = mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True))

    @tool
    async def list_plans() -> str:
        """List ynab plans (budgets). The default plan is used when a tool's plan_id is left out."""
        data = await ynab.get("/plans")
        return compact([
            {**pick(p, "id", "name", "last_modified_on"), "default": p["id"] == plan_id_default}
            for p in data["plans"]
        ])

    @tool
    async def get_accounts(include_closed: bool = False, plan_id: str | None = None) -> str:
        """Accounts with their working, cleared and uncleared balances. Debt accounts are negative.
        Loans include interest rates and minimum payments keyed by the month they took effect.
        Off-budget accounts (on_budget false) are tracking only and don't affect the budget."""
        data = await ynab.get(f"/plans/{plan_id or plan_id_default}/accounts")
        return compact([
            pick(
                a, "id", "name", "type", "on_budget", "closed", "balance", "cleared_balance",
                "uncleared_balance", "last_reconciled_at", "note", "debt_original_balance",
                "debt_interest_rates", "debt_minimum_payments", "debt_escrow_amounts",
            )
            for a in data["accounts"]
            if not a["deleted"] and (include_closed or not a["closed"])
        ])

    @tool
    async def get_month(
        month: str = "current", include_hidden: bool = False, plan_id: str | None = None
    ) -> str:
        """One budget month: income, assigned (budgeted), activity, ready to assign (to_be_budgeted),
        age of money, and every category's assigned/activity/available (balance) plus its target.
        month is YYYY-MM-01 or "current"; ynab's "current" follows UTC, so near midnight at month
        end pass the month explicitly.

        goal_target is per goal period, so read it w goal_cadence (a yearly 1200 is not 1200 a
        month). goal_under_funded is what's still needed this month, goal_overall_left is what's
        left for the whole goal. A snoozed goal (goal_snoozed_at set) isn't counted as underfunded.

        Hidden categories are left out unless include_hidden, except ones that still hold money
        or had activity, which are always shown; hidden_omitted counts the rest."""
        data = (await ynab.get(f"/plans/{plan_id or plan_id_default}/months/{month}"))["month"]
        out = pick(data, "month", "note", "income", "budgeted", "activity", "to_be_budgeted", "age_of_money")
        cats, omitted = [], 0
        for c in data["categories"]:
            if c["deleted"] or c["internal"]:
                continue
            if c["hidden"] and not include_hidden and not c["balance"] and not c["activity"]:
                omitted += 1
                continue
            row = pick(
                c, "id", "category_group_name", "name", "hidden", "budgeted", "activity", "balance",
                "goal_type", "goal_target", "goal_target_date", "goal_under_funded",
                "goal_overall_left", "goal_percentage_complete", "goal_needs_whole_amount",
                "goal_snoozed_at", "note",
            )
            if c.get("goal_type"):
                row["goal_cadence"] = cadence(c)
            cats.append(row)
        out["categories"] = cats
        out["hidden_omitted"] = omitted
        return compact(out)

    @tool
    async def list_months(since: str | None = None, plan_id: str | None = None) -> str:
        """Month-by-month totals (income, assigned, activity, ready to assign, age of money), for
        trends over time. since is YYYY-MM-01 and defaults to 12 months ago. ynab pre-creates next
        month, so the newest row can be a month that hasn't started."""
        if since is None:
            since = (datetime.date.today().replace(day=1) - datetime.timedelta(days=365)).replace(day=1).isoformat()
        data = await ynab.get(f"/plans/{plan_id or plan_id_default}/months")
        return compact([
            pick(m, "month", "income", "budgeted", "activity", "to_be_budgeted", "age_of_money")
            for m in data["months"]
            if not m["deleted"] and m["month"] >= since
        ])

    @tool
    async def find_payees(search: str, plan_id: str | None = None) -> str:
        """Payees whose name contains search (case-insensitive), w their ids for get_transactions'
        payee_id filter. At most 50 matches, so make search more specific if truncated is true.
        Transfer payees have a transfer_account_id."""
        # th full list is thousands of payees, way past wat hermes will show her in one result
        data = await ynab.get(f"/plans/{plan_id or plan_id_default}/payees")
        needle = search.casefold()
        hits = [p for p in data["payees"] if not p["deleted"] and needle in p["name"].casefold()]
        return compact({
            "payees": [pick(p, "id", "name", "transfer_account_id") for p in hits[:50]],
            "total": len(hits),
            "truncated": len(hits) > 50,
        })

    @tool
    async def get_transactions(
        since_date: str | None = None,
        until_date: str | None = None,
        account_id: str | None = None,
        category_id: str | None = None,
        payee_id: str | None = None,
        only_uncategorized_or_unapproved: str | None = None,
        limit: int = 100,
        plan_id: str | None = None,
    ) -> str:
        """Transactions between since_date and until_date (YYYY-MM-DD, both inclusive), newest
        first, at most limit rows. since_date defaults to 30 days ago, or to all history when
        only_uncategorized_or_unapproved is set. For a past period always pass both dates, or the
        newest rows crowd it out; if truncated is true, narrow the range rather than trusting totals.
        Rows are ~350 chars and results past ~50k chars get cut off by the client, so keep limit at
        100 or under and narrow by date range or a filter instead of raising it.

        Filter by at most one of account_id, category_id or payee_id (ids from get_accounts,
        get_month, find_payees). only_uncategorized_or_unapproved is "uncategorized" (on-budget,
        non-transfer rows that need a category) or "unapproved".

        Transfers between accounts have transfer_account_id set and aren't spending; leave them out
        when totaling. Off-budget accounts aren't part of the budget either. Splits list their
        subtransactions; when filtering by category or payee, split parts come back as their own
        rows w type "subtransaction" and a parent_transaction_id instead."""
        plan = plan_id or plan_id_default
        if sum(x is not None for x in (account_id, category_id, payee_id)) > 1:
            raise YnabError("pick at most one of account_id, category_id, payee_id")
        if limit < 1:
            raise YnabError("limit has 2 b at least 1")
        kind = only_uncategorized_or_unapproved
        if kind not in (None, "uncategorized", "unapproved"):
            raise YnabError('only_uncategorized_or_unapproved is "uncategorized" or "unapproved"')
        path = f"/plans/{plan}/transactions"
        if account_id:
            path = f"/plans/{plan}/accounts/{account_id}/transactions"
        elif category_id:
            path = f"/plans/{plan}/categories/{category_id}/transactions"
        elif payee_id:
            path = f"/plans/{plan}/payees/{payee_id}/transactions"
        if since_date is None and kind is None:
            since_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        data = await ynab.get(path, since_date=since_date, until_date=until_date, type=kind)
        txns = [t for t in data["transactions"] if not t["deleted"]]
        if kind == "uncategorized":
            # ynab counts every transfer nd off-budget row as uncategorized, none of those need fixing
            accounts = (await ynab.get(f"/plans/{plan}/accounts"))["accounts"]
            on_budget = {a["id"] for a in accounts if a["on_budget"]}
            txns = [t for t in txns if t["account_id"] in on_budget and not t["transfer_account_id"]]
        txns.sort(key=lambda t: t["date"], reverse=True)
        out = []
        for t in txns[:limit]:
            row = pick(
                t, "id", "date", "amount", "payee_name", "payee_id", "category_name", "category_id",
                "account_name", "account_id", "transfer_account_id", "memo", "cleared", "approved",
                "flag_color", "flag_name", "parent_transaction_id",
            )
            if t.get("type") == "subtransaction":
                row["type"] = "subtransaction"
            subs = [
                pick(s, "amount", "payee_name", "category_name", "category_id", "transfer_account_id", "memo")
                for s in t.get("subtransactions", [])
                if not s.get("deleted")
            ]
            if subs:
                row["subtransactions"] = subs
            out.append(row)
        result = {"transactions": out, "total": len(txns), "truncated": len(txns) > limit}
        if result["truncated"]:
            result["oldest_included"] = out[-1]["date"]
        return compact(result)

    @tool
    async def get_scheduled_transactions(plan_id: str | None = None) -> str:
        """Upcoming scheduled (recurring) transactions. Splits list their subtransactions."""
        data = await ynab.get(f"/plans/{plan_id or plan_id_default}/scheduled_transactions")
        out = []
        for s in data["scheduled_transactions"]:
            if s["deleted"]:
                continue
            row = pick(
                s, "id", "date_next", "frequency", "amount", "payee_name", "category_name",
                "account_name", "transfer_account_id", "memo", "flag_color",
            )
            subs = [
                pick(x, "amount", "payee_id", "category_id", "transfer_account_id", "memo")
                for x in s.get("subtransactions", [])
                if not x.get("deleted")
            ]
            if subs:
                row["subtransactions"] = subs
            out.append(row)
        return compact(out)

    auth_tool = mcp.tool(structured_output=False)

    async def grant_is_dead():
        try:
            await tokens.get(force=True)
        except GrantDead:
            return True
        except YnabError as e:
            raise YnabError(f"cant tell if th current grant still works ({e}), not touching it") from None
        return False

    @auth_tool
    async def ynab_auth_start() -> str:
        """Only when another ynab tool said the grant is dead and ellie needs to reconnect: returns
        a link for ellie to open and approve herself. Give her the link, then pass the code (or the
        whole URL) she sends back to ynab_auth_finish. Never open the link yourself."""
        if not await grant_is_dead():
            return compact({"connected": True, "note": "th grant still works, nothing 2 reconnect"})
        now = time.monotonic()
        for k in [k for k, exp in pending.items() if exp < now]:
            del pending[k]
        state = secrets.token_urlsafe(16)
        pending[state] = now + 15 * 60
        return compact({"connected": False, "url": tokens.authorize_url(state), "expires_in_minutes": 15})

    @auth_tool
    async def ynab_auth_finish(code: str) -> str:
        """Finish reconnecting with the code or redirect URL ellie sent back after opening the
        ynab_auth_start link. Only use what ellie herself sent you."""
        # a code from someone else's ynab account would quietly swap her budget 4 theirs. so: only
        # wen th old grant is really dead, nd only if th new one can see her plan
        if not plan_id:
            raise YnabError("YNAB_PLAN_ID isnt set, so theres no way 2 check whose budget a code is 4")
        if not await grant_is_dead():
            raise YnabError("th current grant still works, refusing 2 replace it")
        reply = code.strip()
        if "code=" in reply:
            query = parse_qs(urlparse(reply).query or reply.split("?", 1)[-1])
            reply = query.get("code", [""])[0]
            state = query.get("state", [None])[0]
            # a bare code or an oob page has no state, but one tht does have it must b ours
            if state is not None and pending.pop(state, 0) < time.monotonic():
                raise YnabError("tht link's state isnt one i handed out (or it expired), start over")
        if not reply:
            raise YnabError("no code in tht")

        async def check(access):
            r = await ynab.get_with(access, "/plans")
            if r.status_code != 200:
                raise YnabError(f"new grant cant list plans: {r.status_code}")
            if plan_id not in {p["id"] for p in r.json()["data"]["plans"]}:
                raise YnabError("new grant cant see ellie's budget, wrong ynab account? not saving it")

        await tokens.exchange(reply, check)
        return compact({"connected": True})

    return mcp


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3740)
    p.add_argument("--plan-id", default=os.environ.get("YNAB_PLAN_ID"))
    p.add_argument(
        "--redirect-uri",
        default=os.environ.get("YNAB_REDIRECT_URI", "urn:ietf:wg:oauth:2.0:oob"),
        help="must match th oauth app's redirect uri",
    )
    p.add_argument(
        "--refresh-token-file",
        type=Path,
        default=Path(os.environ.get("STATE_DIRECTORY", ".")) / "refresh-token",
    )
    args = p.parse_args()

    http = httpx.AsyncClient(timeout=30)
    tokens = Tokens(
        http,
        os.environ["YNAB_CLIENT_ID"],
        os.environ["YNAB_CLIENT_SECRET"],
        args.refresh_token_file,
        args.redirect_uri,
    )
    server = build_server(Ynab(http, tokens), tokens, args.plan_id, args.host, args.port)
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
