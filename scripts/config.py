"""Manage the skill's state + account credentials.

Subcommands:
  show                              dump state.json + current credentials (redacted)
  list-accounts                     list available credential files
  bind --account-id <id>            bind the skill to an account:
                                      1) verify ~/.aixfund/accounts/<id>.json exists
                                      2) read mode + initial_balance from the challenge
                                         endpoint (falls back to /exchange-accounts)
                                      3) write state.json (active_account_id, mode, ...)
                                    Also used for "rebinding" (same command, new id).
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
    fetch_active_exchange,
    http_request,
    list_credential_account_ids,
    load_credentials,
    load_state,
    print_json,
    save_credentials,
    save_state,
)


# Mode inference is data-driven from the challenge endpoint's `program_id`
# (e.g. "standard_5k" / "boost_10k" / "lite_1k" / "payout"), which encodes both
# track and tier exactly — see _mode_from_program_id. The old approach of
# reconstructing the tier from `initial_capital` was removed: on a traded
# account that field can report the current balance, which would pick the wrong
# tier. The only legacy fallback retained is PAYOUT-phase detection from
# /exchange-accounts (the challenge endpoint can't see phase while the aixfund
# sub-object is null pre-upgrade).


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mode_from_program_id(program_id: str) -> str | None:
    """Map the challenge endpoint's `program_id` to a skill mode key.

    program_id already encodes both track and tier (e.g. "standard_5k",
    "boost_10k", "lite_1k"), so this is exact — no capital-to-suffix guessing
    and no Standard-vs-Boost inference from max_drawdown_pct. Returns None for
    an unrecognised / empty value so the caller can fall back.
    """
    if not program_id:
        return None
    pid = program_id.strip().lower()
    if pid in ("payout", "payout_account"):
        return "payout"
    # "standard_5k" / "boost_10k" / "lite_1k" -> "standard-5k" / ...
    parts = pid.split("_")
    if len(parts) == 2 and parts[0] in ("standard", "boost", "lite") and parts[1].endswith("k"):
        return f"{parts[0]}-{parts[1]}"
    return None


def _infer_via_challenge(minimal_cfg: dict, account_id: str) -> tuple[str, int | None] | None:
    """Preferred path: derive (mode, initial_balance) from
    /exchange-accounts/:id/challenge.

    Uses `aixfund.program_id` for the exact mode and `equity.baseline_equity`
    (the funded baseline, which does NOT drift as the account trades — unlike
    the current balance) for initial_balance. Returns None so the caller falls
    back to the legacy /exchange-accounts path when the endpoint is down, or the
    aixfund sub-object is null (pre-upgrade) and so program_id is unavailable.
    """
    path = f"/exchange-accounts/{account_id}/challenge"
    try:
        resp = http_request("GET", path, cfg=minimal_cfg)
    except SystemExit:
        return None  # 503 / network / not deployed -> legacy fallback
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return None

    aixfund = data.get("aixfund") or {}
    mode = _mode_from_program_id(aixfund.get("program_id") or "")
    if not mode:
        return None  # aixfund null / unknown program_id -> legacy fallback

    # baseline_equity is the funded baseline (== initial_capital); fall back to
    # the equity sub-object's initial_capital if baseline is absent.
    equity = data.get("equity") or {}
    try:
        baseline = int(float(equity.get("baseline_equity") or equity.get("initial_capital") or 0))
    except (TypeError, ValueError):
        baseline = 0
    return mode, (baseline or None)


def _infer_mode_and_balance(token: str, base_url_http: str, account_id: str) -> tuple[str, int | None]:
    """Derive (mode, initial_balance) for the given account.

    Challenge info comes from /exchange-accounts/:id/challenge first
    (`program_id` is an exact mode, `baseline_equity` is the funded baseline
    that doesn't drift with trading). The legacy /exchange-accounts path is the
    fallback — it covers Payout phase (which lives in the aixfund sub-object and
    is null pre-upgrade) and works when the challenge endpoint is unavailable.
    """
    minimal_cfg = {"token": token, "base_url_http": base_url_http, "exchange_account_id": account_id}

    via_challenge = _infer_via_challenge(minimal_cfg, account_id)
    if via_challenge is not None:
        return via_challenge

    # Fallback: legacy /exchange-accounts. Only used when the challenge endpoint
    # is unavailable OR its aixfund sub-object is null (pre-upgrade) so
    # program_id is missing. We deliberately do NOT reconstruct the tier from
    # capital here: on a traded account `initial_capital` can report the current
    # balance rather than the funded amount, which would pick the wrong tier (or
    # crash). The only thing this fallback derives is PAYOUT phase, which the
    # challenge path can't see while aixfund is null. For a non-payout account
    # we ask the user to specify the mode explicitly instead of guessing.
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
    if phase == "PAYOUT":
        try:
            initial_capital = int(float(acc.get("initial_capital") or 0))
        except (TypeError, ValueError):
            initial_capital = 0
        return "payout", (initial_capital or None)

    die(
        "Could not determine challenge mode: the /exchange-accounts/:id/challenge "
        "endpoint did not return a program_id (it may be unavailable, or aixfund "
        "has not yet populated the aixfund sub-object). Re-run once it is "
        "available, or set the mode explicitly:\n"
        "  python3 config.py bind --account-id <id> --skip-lookup "
        "--mode <standard-NNk|boost-NNk|lite-1k> --initial-balance <amount>"
    )


def _redact_token(token: str) -> str:
    if not token or len(token) < 12:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_show(_args) -> None:
    out: dict[str, Any] = {
        "skill_state_path": str(STATE_PATH),
        "credentials_dir": str(CREDENTIALS_DIR),
        "available_accounts": list_credential_account_ids(),
    }

    # Read state.json directly so a corrupt file does not prevent `show`
    # from surfacing the available credentials — `show` is the tool of last
    # resort when troubleshooting bind problems.
    state: dict[str, Any] = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            out["state"] = None
            out["state_error"] = f"{type(e).__name__}: {e}"
            out["recovery_hint"] = (
                "Delete state.json and rebind: "
                "`python3 scripts/config.py bind --account-id <id>`."
            )
            print_json(out)
            return

    out["state"] = state
    active_id = state.get("active_account_id")
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

    # Cache active_exchange so scripts don't need to hit /market/metadata
    # on every run. Best-effort — bind shouldn't fail if metadata is down.
    try:
        active_exchange = fetch_active_exchange(
            cfg={"token": creds["token"], "base_url_http": creds["base_url_http"],
                 "exchange_account_id": account_id}
        )
        if active_exchange:
            new_state["active_exchange"] = active_exchange
    except SystemExit:
        # http_request -> die() raises SystemExit. Don't block bind on this.
        pass

    save_state(new_state)

    action = "Rebound" if rebinding else "Bound"
    print(f"{action} skill to account {account_id} (mode={mode}, initial_balance={initial_balance})",
          file=sys.stderr)
    if rebinding:
        print(f"  (previous active: {prev_active})", file=sys.stderr)
    print_json({"state": new_state, "skill_state_path": str(STATE_PATH)})


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
    for k in ("mode", "initial_balance"):
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
