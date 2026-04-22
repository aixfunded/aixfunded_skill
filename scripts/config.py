"""Manage the skill's state + account credentials.

Subcommands:
  show                              dump state.json + current credentials (redacted)
  list-accounts                     list available credential files
  bind --account-id <id>            bind the skill to an account:
                                      1) verify ~/.aixfund/accounts/<id>.json exists
                                      2) call /exchange-accounts to infer mode + initial_balance
                                      3) write state.json (active_account_id, mode, ...)
                                    Also used for "rebinding" (same command, new id).
  reset-challenge                   clear challenge_start_ts / challenge_start_date_utc
                                    (e.g. platform reset the challenge)
  migrate                           move legacy ~/.aixfund/config.json into the new
                                    accounts/<id>.json + state.json layout

Legacy:
  bootstrap --token <...>           agent-driven first-time setup (token passes
                                    through the agent). Writes both credentials and
                                    state. Prefer the terminal snippet + `bind` flow.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _common import (
    CREDENTIALS_DIR,
    CREDENTIAL_REQUIRED,
    DEFAULT_BASE_URLS,
    LEGACY_CONFIG_PATH,
    STATE_PATH,
    credential_path,
    die,
    http_request,
    list_credential_account_ids,
    load_credentials,
    load_state,
    print_json,
    save_credentials,
    save_state,
)


# Known challenge tiers (initial_capital -> mode)
INITIAL_CAPITAL_TO_MODE = {
    1000: "lite",
    10000: "standard-10k",
    20000: "standard-20k",
    30000: "standard-30k",
    50000: "standard-50k",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_mode_and_balance(token: str, base_url_http: str, account_id: str) -> tuple[str, int | None]:
    """Call /exchange-accounts and derive (mode, initial_balance) for the given account."""
    minimal_cfg = {"token": token, "base_url_http": base_url_http, "exchange_account_id": account_id}
    resp = http_request("GET", "/exchange-accounts", cfg=minimal_cfg)
    accounts = resp.get("data", {}).get("exchange_accounts", []) or []
    if not accounts:
        die("Token is valid but no exchange accounts are authorized for it.")

    target = [a for a in accounts if str(a.get("exchange_account_id")) == str(account_id)]
    if not target:
        available = [str(a.get("exchange_account_id")) for a in accounts]
        die(
            f"account_id {account_id} is not authorized for this token. "
            f"Available accounts: {available}"
        )
    acc = target[0]

    phase = (acc.get("account_phase") or "").upper()
    try:
        initial_capital = int(float(acc.get("initial_capital") or 0))
    except (TypeError, ValueError):
        initial_capital = 0

    if phase == "PAYOUT":
        return "payout", (initial_capital or None)
    mode = INITIAL_CAPITAL_TO_MODE.get(initial_capital)
    if not mode:
        die(
            f"Cannot infer challenge mode: account initial_capital={initial_capital} "
            f"does not match any known tier {sorted(INITIAL_CAPITAL_TO_MODE)}."
        )
    return mode, initial_capital


def _redact_token(token: str) -> str:
    if not token or len(token) < 12:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_show(_args) -> None:
    state = load_state()
    active_id = state.get("active_account_id")
    out: dict[str, Any] = {
        "skill_state_path": str(STATE_PATH),
        "credentials_dir": str(CREDENTIALS_DIR),
        "state": state,
        "available_accounts": list_credential_account_ids(),
    }
    if active_id:
        try:
            creds = load_credentials(active_id)
            out["active_credentials"] = {
                **creds,
                "token": _redact_token(creds.get("token", "")),
            }
        except SystemExit:
            out["active_credentials"] = f"<missing file for {active_id}>"
    print_json(out)


def cmd_list_accounts(_args) -> None:
    ids = list_credential_account_ids()
    state = load_state()
    print_json({
        "available_accounts": ids,
        "active_account_id": state.get("active_account_id"),
    })


def cmd_bind(args) -> None:
    """Bind the skill to an account (first-time setup OR switching accounts).

    Expects ~/.aixfund/accounts/<account_id>.json to already exist (written
    by the STEP 2 terminal snippet).
    """
    account_id = str(args.account_id)
    creds = load_credentials(account_id)  # exits if missing

    if not args.skip_lookup:
        mode, initial_balance = _infer_mode_and_balance(
            token=creds["token"],
            base_url_http=creds["base_url_http"],
            account_id=account_id,
        )
    else:
        mode, initial_balance = args.mode, args.initial_balance

    state = load_state()
    prev_active = state.get("active_account_id")
    rebinding = prev_active and prev_active != account_id

    new_state: dict[str, Any] = {
        "active_account_id": account_id,
        "mode": mode,
        "initial_balance": initial_balance,
    }
    # Preserve the stamped challenge start only if we're NOT switching accounts.
    if not rebinding:
        for k in ("challenge_start_ts", "challenge_start_date_utc"):
            if state.get(k):
                new_state[k] = state[k]

    save_state(new_state)

    action = "Rebound" if rebinding else "Bound"
    print(f"{action} skill to account {account_id} (mode={mode}, initial_balance={initial_balance})",
          file=sys.stderr)
    if rebinding:
        print(f"  (previous active: {prev_active}; challenge_start cleared)", file=sys.stderr)
    print_json({"state": new_state, "skill_state_path": str(STATE_PATH)})


def cmd_reset_challenge(_args) -> None:
    state = load_state()
    cleared = {k: state.pop(k, None) for k in ("challenge_start_ts", "challenge_start_date_utc")}
    save_state(state)
    print_json({"cleared": cleared, "state": state})


def cmd_migrate(_args) -> None:
    """Move legacy ~/.aixfund/config.json into the new layout."""
    if not LEGACY_CONFIG_PATH.exists():
        die(f"No legacy file at {LEGACY_CONFIG_PATH}; nothing to migrate.")
    try:
        legacy = json.loads(LEGACY_CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        die(f"Failed to parse {LEGACY_CONFIG_PATH}: {e}")

    account_id = str(legacy.get("exchange_account_id") or "").strip()
    if not account_id:
        die(f"Legacy config lacks exchange_account_id; cannot migrate.")

    creds = {
        "token": legacy.get("token"),
        "exchange_account_id": account_id,
        "base_url_http": legacy.get("base_url_http") or DEFAULT_BASE_URLS["base_url_http"],
        "base_url_ws_private": legacy.get("base_url_ws_private") or DEFAULT_BASE_URLS["base_url_ws_private"],
        "base_url_ws_public": legacy.get("base_url_ws_public") or DEFAULT_BASE_URLS["base_url_ws_public"],
    }
    missing = [k for k in CREDENTIAL_REQUIRED if not creds.get(k)]
    if missing:
        die(f"Legacy config missing {missing}; cannot migrate.")
    save_credentials(account_id, creds)

    state: dict[str, Any] = {"active_account_id": account_id}
    for k in ("mode", "initial_balance", "challenge_start_ts", "challenge_start_date_utc"):
        if legacy.get(k) is not None:
            state[k] = legacy[k]
    save_state(state)

    # Rename the legacy file rather than delete, in case the user wants to inspect it
    backup = LEGACY_CONFIG_PATH.with_suffix(".json.migrated")
    LEGACY_CONFIG_PATH.rename(backup)

    print(
        f"Migrated legacy {LEGACY_CONFIG_PATH.name} → credentials + state. "
        f"Backup at {backup}.",
        file=sys.stderr,
    )
    print_json({
        "credentials_path": str(credential_path(account_id)),
        "state_path": str(STATE_PATH),
        "state": state,
    })


def cmd_bootstrap(args) -> None:
    """Agent-driven first-time setup (token passes through the agent).

    Only use when the platform's STEP 2 terminal snippet is unavailable.
    Writes credentials + state in one shot.
    """
    base_urls = DEFAULT_BASE_URLS
    minimal_cfg = {"token": args.token, **base_urls}
    resp = http_request("GET", "/exchange-accounts", cfg=minimal_cfg)
    accounts = resp.get("data", {}).get("exchange_accounts", []) or []
    if not accounts:
        die("Token is valid but no exchange accounts are authorized for it.")

    if len(accounts) == 1:
        account = accounts[0]
    else:
        if not args.exchange_account_id:
            listing = "\n".join(
                f"  - {a.get('exchange_account_id')} "
                f"(phase={a.get('account_phase')}, initial_capital={a.get('initial_capital')})"
                for a in accounts
            )
            die(f"Multiple accounts authorized; pass --exchange-account-id:\n{listing}")
        match = [a for a in accounts if str(a.get("exchange_account_id")) == str(args.exchange_account_id)]
        if not match:
            die(
                f"--exchange-account-id {args.exchange_account_id} not authorized. Available: "
                f"{[a.get('exchange_account_id') for a in accounts]}"
            )
        account = match[0]

    account_id = str(account.get("exchange_account_id"))

    # Write credentials
    creds = {
        "token": args.token,
        "exchange_account_id": account_id,
        **base_urls,
    }
    save_credentials(account_id, creds)

    # Infer + persist state via bind
    args_ns = argparse.Namespace(
        account_id=account_id, skip_lookup=False, mode=None, initial_balance=None,
    )
    cmd_bind(args_ns)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Manage the AiXFund skill state + account credentials")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show").set_defaults(func=cmd_show)
    sub.add_parser("list-accounts").set_defaults(func=cmd_list_accounts)

    sp_bind = sub.add_parser(
        "bind",
        help="Bind (or rebind) the skill to an account. The account's credentials "
             "must already be in ~/.aixfund/accounts/<id>.json.",
    )
    sp_bind.add_argument("--account-id", required=True)
    sp_bind.add_argument("--skip-lookup", action="store_true",
                         help="Don't call /exchange-accounts; requires --mode")
    sp_bind.add_argument("--mode", help="Used only with --skip-lookup")
    sp_bind.add_argument("--initial-balance", type=int, help="Used only with --skip-lookup")
    sp_bind.set_defaults(func=cmd_bind)

    sub.add_parser("reset-challenge",
                   help="Clear challenge_start_ts (e.g. after the platform reset the challenge)"
                   ).set_defaults(func=cmd_reset_challenge)

    sub.add_parser("migrate",
                   help="Move legacy ~/.aixfund/config.json into accounts/<id>.json + state.json"
                   ).set_defaults(func=cmd_migrate)

    sp_boot = sub.add_parser(
        "bootstrap",
        help="Legacy agent-driven first-time setup (token passes through the agent).",
    )
    sp_boot.add_argument("--token", required=True)
    sp_boot.add_argument("--exchange-account-id", default=None,
                         help="Required only when the token authorizes multiple accounts.")
    sp_boot.set_defaults(func=cmd_bootstrap)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
