"""Shared utilities: config loading, HTTP calls, error formatting.

Configuration lives in two places:

  ~/.aixfund/accounts/<exchange_account_id>.json   -- credentials only
      (token + exchange_account_id + base_url_http / _ws_private / _ws_public)
      Written by the STEP 2 terminal snippet; scripts read-only from here.

  <skill-root>/state.json                          -- per-skill runtime state
      (active_account_id + mode + initial_balance + challenge_start_ts + ...)
      Written by `config.py bind` and by place_order.py on first order.

This split means:
  - Credentials never get overwritten by challenge-state changes.
  - The skill directory is the "current binding"; install two skill copies
    to operate two accounts in parallel.
  - Deleting state.json resets the challenge (not the credentials).

Public API:
    load_config() -> merged dict with token+URLs+mode+challenge fields
    save_state(state) / load_state() -> raw state.json R/W
    load_credentials(account_id) -> raw credentials file
    http_request(...), die(), print_json(), server_utc_ts_from_headers()
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error
import urllib.parse

# Skill root = the directory that contains scripts/_common.py
SKILL_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = SKILL_ROOT / "state.json"

CREDENTIALS_DIR = Path.home() / ".aixfund" / "accounts"
LEGACY_CONFIG_PATH = Path.home() / ".aixfund" / "config.json"

# Credential fields required for HTTP calls to work.
CREDENTIAL_REQUIRED = ["token", "exchange_account_id", "base_url_http"]

# Placeholders used only by legacy `config.py bootstrap` / `init` when the
# caller doesn't pass explicit URLs. The normal flow (STEP 2 terminal snippet +
# `config.py bind`) writes real URLs from the platform into
# ~/.aixfund/accounts/<id>.json and never consults these defaults.
# Real endpoints come from https://aixfunded.com/app/agent-api.
DEFAULT_BASE_URLS = {
    "base_url_http": "http://<AIXFUND_HOST>/api/v1",
    "base_url_ws_private": "ws://<AIXFUND_HOST>/realtime_private",
    "base_url_ws_public": "ws://<AIXFUND_HOST>/realtime_public",
}


# ---------------------------------------------------------------------------
# State (skill-local)
# ---------------------------------------------------------------------------

def load_state() -> dict[str, Any]:
    """Return the skill's state.json contents, or {} if absent."""
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError as e:
        die(f"Failed to parse {STATE_PATH}: {e}")


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Credentials (~/.aixfund/accounts/<id>.json)
# ---------------------------------------------------------------------------

def list_credential_account_ids() -> list[str]:
    """Return account_ids for every credential file under ~/.aixfund/accounts/."""
    if not CREDENTIALS_DIR.is_dir():
        return []
    return sorted(p.stem for p in CREDENTIALS_DIR.glob("*.json"))


def credential_path(account_id: str) -> Path:
    return CREDENTIALS_DIR / f"{account_id}.json"


def load_credentials(account_id: str) -> dict[str, Any]:
    """Read ~/.aixfund/accounts/<id>.json. Exit if missing or invalid."""
    path = credential_path(account_id)
    if not path.exists():
        die(
            f"Credentials not found: {path}\n"
            f"Paste the STEP 2 terminal snippet from https://aixfunded.com/app/agent-api "
            f"to create it."
        )
    try:
        creds = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        die(f"Failed to parse {path}: {e}")
    missing = [k for k in CREDENTIAL_REQUIRED if not creds.get(k)]
    if missing:
        die(
            f"Credentials at {path} missing required fields: {missing}. "
            f"Re-paste the STEP 2 snippet to rewrite it."
        )
    return creds


def save_credentials(account_id: str, creds: dict[str, Any]) -> None:
    """Write ~/.aixfund/accounts/<id>.json (600 on Unix)."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    path = credential_path(account_id)
    path.write_text(json.dumps(creds, indent=2, ensure_ascii=False))
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows ACLs don't respect POSIX mode; home dir already restricts


# ---------------------------------------------------------------------------
# Merged config (what business scripts see)
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Return the merged config: credentials + state for the active account.

    Credentials: ~/.aixfund/accounts/<active_account_id>.json
    State:       <skill>/state.json
    """
    state = load_state()
    active_id = state.get("active_account_id")
    if not active_id:
        available = list_credential_account_ids()
        hint_available = f" Available credentials: {available}." if available else ""
        die(
            f"No active account bound to this skill.\n"
            f"Ask the user for their account id and run:\n"
            f"  python3 scripts/config.py bind --account-id <id>\n"
            f"First-time setup: see https://aixfunded.com/app/agent-api.{hint_available}"
        )

    creds = load_credentials(active_id)
    cfg: dict[str, Any] = {}
    cfg.update(creds)
    cfg.update({k: v for k, v in state.items() if k != "active_account_id"})
    cfg["exchange_account_id"] = active_id  # credentials file is authoritative
    return cfg


def save_config(_cfg: dict[str, Any]) -> None:
    """Deprecated. Use save_state() / save_credentials() explicitly.

    Kept so legacy callers that still merge everything into one dict don't
    silently lose data. Splits the merged dict back into state-only keys.
    """
    # Extract only state-managed fields to avoid leaking credentials into state
    state_keys = {
        "active_account_id", "mode", "initial_balance",
        "challenge_start_ts", "challenge_start_date_utc",
    }
    state = {k: v for k, v in _cfg.items() if k in state_keys}
    # Preserve existing active_account_id if caller didn't set one
    if "active_account_id" not in state:
        prev = load_state()
        if prev.get("active_account_id"):
            state["active_account_id"] = prev["active_account_id"]
    save_state(state)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
    timeout: int = 30,
    return_headers: bool = False,
) -> Any:
    """Send an HTTP request to the propdesk API and return the parsed JSON.

    - method: GET / POST
    - path: API path starting with `/`, e.g. `/createOrder`
    - query: query string parameters
    - json_body: POST body
    - cfg: config dict; loaded automatically if None
    - return_headers: if True, returns (parsed_body, response_headers_dict).
      Callers that need the server `Date` header (e.g. to stamp the challenge
      start time) pass this.
    """
    if cfg is None:
        cfg = load_config()

    base = cfg["base_url_http"].rstrip("/")
    url = base + path
    if query:
        q = {k: v for k, v in query.items() if v is not None and v != ""}
        if q:
            url += "?" + urllib.parse.urlencode(q)

    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }
    data = json.dumps(json_body).encode() if json_body is not None else None

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    response_headers: dict[str, str] = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            response_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            err = json.loads(body)
        except json.JSONDecodeError:
            err = {"code": e.code, "msg": body or e.reason}
        die(_format_http_error(e.code, err, method, url))
    except urllib.error.URLError as e:
        die(f"Network error calling {method} {url}: {e.reason}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        die(f"Response is not valid JSON: {e}\nRaw response: {body[:500]}")

    if isinstance(parsed, dict) and parsed.get("code") not in (0, None):
        die(_format_business_error(parsed, method, url))

    if return_headers:
        return parsed, response_headers
    return parsed


def server_utc_ts_from_headers(response_headers: dict[str, str]) -> int:
    """Parse HTTP response `Date` header into a UTC unix timestamp (seconds).

    Falls back to the local clock (assumed UTC-synced) when the header is
    absent or unparseable, emitting a warning to stderr. Used to stamp the
    challenge start time when the user places their first order.
    """
    date_header = response_headers.get("Date") or response_headers.get("date")
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.astimezone(timezone.utc).timestamp())
        except (TypeError, ValueError) as e:
            print(
                f"warn: could not parse server Date header ({date_header!r}): {e}; "
                "falling back to local UTC clock",
                file=sys.stderr,
            )
    else:
        print(
            "warn: server response has no Date header; "
            "falling back to local UTC clock",
            file=sys.stderr,
        )
    return int(datetime.now(timezone.utc).timestamp())


# ---------------------------------------------------------------------------
# Errors / output
# ---------------------------------------------------------------------------

def _format_http_error(status: int, err: dict, method: str, url: str) -> str:
    code = err.get("code", status)
    msg = err.get("msg", "")
    hint = ""
    if status == 401 or code == 10002:
        hint = "\n-> Token invalid or missing. Re-paste the STEP 2 snippet from https://aixfunded.com/app/agent-api to refresh the account's credentials."
    elif status == 403 or code == 10003:
        hint = "\n-> Permission denied; the bound account may not be authorized. Run `python3 scripts/auth_check.py` to list authorized accounts."
    elif status == 429 or code == 10008:
        hint = "\n-> Rate limit hit (max 5 orders per second per account). Slow down requests."
    return f"HTTP {status} on {method} {url}\n  code={code} msg={msg}{hint}"


def _format_business_error(parsed: dict, method: str, url: str) -> str:
    return (
        f"Business error on {method} {url}\n  "
        f"code={parsed.get('code')} msg={parsed.get('msg')}"
    )


def die(msg: str, exit_code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(exit_code)


def print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))
