"""Risk snapshot: combines /portfolio/balances + /positions and compares
against per-mode thresholds. Output schema matches spec section 5.2.
"""
from __future__ import annotations

from datetime import datetime, timezone

from _common import get_active_exchange, http_request, load_config, print_json


# Source: aixfunded.com/challenge/rules (authoritative) + the 2026-05-14
# parameter update.
#
# Boost and Standard share the same threshold table at the challenge stage
# per the live rules page: profit 10%, max-loss 6%, daily-drawdown 3%,
# valid days >= 7, no time limit. The only difference between the two
# tracks at challenge stage is the Boost Bonus paid on top of the first
# Payout (informational, see challenge-rules.md). An earlier internal
# Boost MRD listed stricter 12% / 5% thresholds; that version is
# superseded by the public rules page.
#
# Headline changes from the pre-2026-05-14 version (Standard):
#   - 10-day evaluation window REMOVED.
#   - Payout split: 70% -> 80% (informational; not threshold-based).
# And for Lite:
#   - profit target 8% -> 12%, max loss 5% -> 3%.
_STANDARD_THRESHOLDS = {
    "profit_target_pct": 10, "max_loss_pct": 6, "daily_drawdown_pct": 3,
    "valid_trading_days_required": 7, "challenge_period_days": None,
}
_BOOST_THRESHOLDS = dict(_STANDARD_THRESHOLDS)

THRESHOLDS_BY_MODE = {
    "lite": {
        "profit_target_pct": 12,
        "max_loss_pct": 3,
        "daily_drawdown_pct": None,
        "valid_trading_days_required": None,
        "challenge_period_days": None,
    },
    # Threshold values do not depend on capital — only on the track
    # (Standard vs Boost). All tier names a real account might carry are
    # registered here so `bind` never falls off a missing-key error.
    # The marketing literature retires some sizes from time to time, but
    # the live backend still issues accounts at those sizes (e.g. a $30k
    # Standard account exists on testnet as of 2026-05-19).
    "standard-5k":  dict(_STANDARD_THRESHOLDS),
    "standard-10k": dict(_STANDARD_THRESHOLDS),
    "standard-15k": dict(_STANDARD_THRESHOLDS),
    "standard-20k": dict(_STANDARD_THRESHOLDS),
    "standard-25k": dict(_STANDARD_THRESHOLDS),
    "standard-30k": dict(_STANDARD_THRESHOLDS),
    "standard-50k": dict(_STANDARD_THRESHOLDS),
    "boost-5k":  dict(_BOOST_THRESHOLDS),
    "boost-10k": dict(_BOOST_THRESHOLDS),
    "boost-15k": dict(_BOOST_THRESHOLDS),
    "boost-20k": dict(_BOOST_THRESHOLDS),
    "boost-25k": dict(_BOOST_THRESHOLDS),
    "boost-30k": dict(_BOOST_THRESHOLDS),
    "boost-50k": dict(_BOOST_THRESHOLDS),
    "payout": {
        # Payout-stage thresholds per aixfunded.com/challenge/rules:
        # profit target is N/A (trader chooses when to request payout);
        # max-loss 6%, daily-drawdown 3%, valid trading days >= 7. Both
        # hard limits are "hard violations" — one breach closes the
        # account, no warning / no second-strike grace.
        "profit_target_pct": None,
        "max_loss_pct": 6, "daily_drawdown_pct": 3,
        "valid_trading_days_required": 7,
        "challenge_period_days": None,
    },
}

RULE_REMINDERS = [
    "Hold time >= 1 minute (server marks sub-minute closes as a soft violation; "
    "the offending order is rolled back but the account survives).",
    "Forbidden: multi-account trading, hedging across accounts, quote-delay exploits, "
    "high-frequency cancel/replace, third-party-managed accounts, manual/Agent boundary bypass.",
    "Leverage caps: Challenge 10X / Payout 5X (post 2026-05-14 rules page).",
    "Rate limit: max 5 orders per second per account.",
    "Max-loss and daily-drawdown are HARD violations: one breach fails the challenge "
    "or recalls the Payout account; no warning, no waiver.",
    "Inactivity: account is suspended after 30 calendar days without a real fill. "
    "Logins, market data, agent connect, placing/cancelling orders, deposits and "
    "auto-liquidations do NOT count as activity — only an executed trade resets the clock.",
    "Exploit duty: if you spot a backend bug / mispricing / unintended behavior, "
    "report it. Profits from exploiting it can be clawed back.",
]


def _status(current: float, limit: float | None, *, warn_ratio: float = 0.8) -> str:
    if limit is None or limit == 0:
        return "n/a"
    # Round to 2dp before compare so status agrees with the displayed value
    # and float drift can't flip "ok" -> "violated" by a microscopic margin.
    ratio = round(current, 2) / limit
    if ratio >= 1:
        return "violated"
    if ratio >= warn_ratio:
        return "warning"
    return "ok"


def _to_float(v, default=None):
    """Parse a money/percent string field; '' / None / bad -> default."""
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fetch_challenge(cfg) -> dict | None:
    """Call GET /exchange-accounts/:id/challenge — the merged assessment view
    (aixfund business status + equity + risk). Returns the `data` object, or
    None if the endpoint is unavailable (503 / network) so the caller can fall
    back to the compute-from-balances path.

    The account id is a PATH param here, not a ?exchange_account_id= query.
    """
    path = f"/exchange-accounts/{cfg['exchange_account_id']}/challenge"
    try:
        resp = http_request("GET", path, cfg=cfg)
    except SystemExit:
        # http_request -> die() on any HTTP/business error. Don't block the
        # snapshot — fall back to the legacy compute path.
        return None
    data = resp.get("data") if isinstance(resp, dict) else None
    return data if isinstance(data, dict) else None


def main() -> None:
    cfg = load_config()
    mode = cfg.get("mode", "")
    th = THRESHOLDS_BY_MODE.get(mode, {})

    # Prefer the merged /exchange-accounts/:id/challenge endpoint: it exposes
    # fields the legacy compute path could only stub out (max_cumulative_loss,
    # effective trading days, live AI reasoning score, business status). It can
    # return null sub-objects or 503 if an upstream is down, so everything below
    # gracefully falls back to /portfolio/balances + /positions.
    challenge = fetch_challenge(cfg)
    ch_aixfund = (challenge or {}).get("aixfund") or {}
    ch_equity = (challenge or {}).get("equity") or {}
    ch_risk = (challenge or {}).get("risk") or {}
    used_challenge = False

    bal_resp = http_request("GET", "/portfolio/balances",
                            query={"exchange_account_id": cfg["exchange_account_id"]}, cfg=cfg)
    balances = bal_resp.get("data", {}).get("balances", [])
    bal = balances[0] if balances else {}
    # total_equity_value already includes unrealized_pnl per the exchange's
    # balance contract (wallet_balance + unrealized_pnl). Use it as the PnL
    # basis; expose the components separately so agents can see the breakdown.
    wallet_balance = float(bal.get("wallet_balance", 0))
    unrealized_pnl = float(bal.get("unrealized_pnl", 0))
    realized_pnl = float(bal.get("realized_pnl", 0))

    # Equity / current PnL: prefer the challenge endpoint's current_equity
    # (risk-server, mark-priced) and fall back to the balance contract.
    ch_equity_val = _to_float(ch_equity.get("current_equity"))
    if ch_equity_val is not None:
        total_equity = ch_equity_val
        used_challenge = True
    else:
        total_equity = float(bal.get("total_equity_value", 0))

    initial_balance = (
        _to_float(ch_equity.get("initial_capital"))
        or cfg.get("initial_balance")
        or total_equity
    )

    pos_resp = http_request("GET", "/positions",
                            query={"exchange_account_id": cfg["exchange_account_id"]}, cfg=cfg)
    positions = pos_resp.get("data", {}).get("positions", [])
    open_pos_count = len(positions)

    pnl_pct = ((total_equity - initial_balance) / initial_balance * 100) if initial_balance else 0

    # Max cumulative loss: the challenge endpoint's max_cumulative_loss_pct is
    # the authoritative Rules-2.0 figure (same basis as the red line, includes
    # the historical trough). Fall back to instantaneous loss from equity.
    ch_cum_loss = _to_float(ch_risk.get("max_cumulative_loss_pct"))
    if ch_cum_loss is not None:
        loss_pct = ch_cum_loss
        used_challenge = True
    else:
        loss_pct = max(0, -pnl_pct)

    # Challenge period is stamped by place_order.py at the first successful
    # order placement (server Date header, UTC seconds). If no order has been
    # placed yet, the challenge hasn't started.
    start_ts = cfg.get("challenge_start_ts")
    # Back-compat: migrate legacy "challenge_start_date" (YYYY-MM-DD) on the fly
    # if the new field is absent.
    if not start_ts and cfg.get("challenge_start_date"):
        try:
            legacy = datetime.strptime(cfg["challenge_start_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ts = int(legacy.timestamp())
        except ValueError:
            start_ts = None

    elapsed_days = remaining_days = challenge_started = None
    start_date_utc = cfg.get("challenge_start_date_utc") or cfg.get("challenge_start_date")
    if start_ts and th.get("challenge_period_days"):
        challenge_started = True
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - start_dt).days
        elapsed_days = elapsed
        remaining_days = max(0, th["challenge_period_days"] - elapsed)
        start_date_utc = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif th.get("challenge_period_days"):
        challenge_started = False

    # Active exchange is chosen at runtime by the backend (post 2026-05-15).
    # Pull from state.json cache; refresh from /market/metadata if absent.
    try:
        active_exchange = get_active_exchange(cfg=cfg)
    except SystemExit:
        active_exchange = None

    # --- daily drawdown: prefer challenge endpoint's last_daily_drawdown_pct.
    # It is the daily_drawdown worker's 08:00-UTC snapshot, same basis as the
    # red line (breach when last < -max). Semantically <= 0; "0" = flat/profit/
    # first day. NOTE: 24h discrete sample, not an intraday real-time value.
    ch_last_dd = _to_float(ch_risk.get("last_daily_drawdown_pct"))
    if ch_last_dd is not None:
        used_challenge = True
        daily_dd_block = {
            "limit_pct": th.get("daily_drawdown_pct"),
            "last_daily_drawdown_pct": round(ch_last_dd, 4),
            "status": _status(abs(ch_last_dd), th.get("daily_drawdown_pct")),
            "note": "From challenge endpoint (daily_drawdown worker, 08:00 UTC snapshot); "
                    "not an intraday real-time value.",
        }
    else:
        daily_dd_block = {
            "limit_pct": th.get("daily_drawdown_pct"),
            "note": "Compute from /pnl/closed + intraday balance change; not auto-derived in fallback.",
        }

    # --- valid trading days: prefer challenge endpoint's
    # effective_trading_days_so_far. Per the API doc these aixfund fields are
    # "pending an aixfund schema extension" and may come back 0 / "" until then,
    # so only trust a positive value; otherwise keep the threshold + note.
    eff_days = ch_aixfund.get("effective_trading_days_so_far")
    req_days = ch_aixfund.get("min_trading_days") or th.get("valid_trading_days_required")
    if isinstance(eff_days, (int, float)) and eff_days > 0:
        used_challenge = True
        valid_days_block = {
            "required": req_days,
            "achieved": int(eff_days),
            "remaining": max(0, int(req_days) - int(eff_days)) if req_days else None,
        }
    else:
        valid_days_block = {
            "required": req_days,
            "achieved": int(eff_days) if isinstance(eff_days, (int, float)) else None,
            "note": "effective_trading_days_so_far pending aixfund schema extension "
                    "(may report 0 until enabled); aggregate /trades per day to verify.",
        }

    # --- business status + live AI reasoning score (challenge endpoint only).
    business = None
    if challenge is not None and ch_aixfund:
        llm_score = _to_float(ch_aixfund.get("agent_llm_score"))
        business = {
            "status": ch_aixfund.get("status"),
            "program_id": ch_aixfund.get("program_id"),
            "trading_mode": ch_aixfund.get("trading_mode"),
            "agent_llm_score": llm_score,
            "agent_llm_score_status": (
                "n/a" if llm_score is None
                else "below_threshold" if llm_score < 60 else "ok"
            ),
            "min_holding_seconds": ch_risk.get("min_holding_seconds"),
        }

    output = {
        "exchange_account_id": cfg["exchange_account_id"],
        "active_exchange": active_exchange,
        "mode": mode,
        # Where the equity / loss / daily-dd / valid-days figures came from:
        # "challenge_endpoint" if any field was sourced from
        # /exchange-accounts/:id/challenge, else "fallback_compute".
        "data_source": "challenge_endpoint" if used_challenge else "fallback_compute",
        "initial_balance": initial_balance,
        "total_equity_value": total_equity,
        "wallet_balance": wallet_balance,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "current_pnl_pct": round(pnl_pct, 2),
        "profit_target_pct": th.get("profit_target_pct"),
        "business": business,
        "thresholds": {
            "max_loss": {
                "limit_pct": th.get("max_loss_pct"),
                "current_pct": round(loss_pct, 2),
                "status": _status(loss_pct, th.get("max_loss_pct")),
            },
            "daily_drawdown": daily_dd_block,
            "valid_trading_days": valid_days_block,
            "challenge_period_days": {
                "limit": th.get("challenge_period_days"),
                "elapsed": elapsed_days,
                "remaining": remaining_days,
                "challenge_started": challenge_started,
                "start_date_utc": start_date_utc,
                "note": (
                    None if challenge_started is not False
                    else "Challenge starts at the first successful order placement (stamped in UTC)."
                ),
            },
        },
        "open_positions_count": open_pos_count,
        "rule_reminders": RULE_REMINDERS,
    }
    print_json(output)


if __name__ == "__main__":
    main()
