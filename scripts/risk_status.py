"""Risk snapshot: combines /portfolio/balances + /positions and compares
against per-mode thresholds. Output schema matches spec section 5.2.
"""
from __future__ import annotations

from datetime import datetime, timezone

from _common import get_active_exchange, http_request, load_config, print_json


# Source: aixfunded.com/plans + the 2026-05-14 parameter update + the
# Boost mode MRD.
#
# Headline changes from the pre-2026-05-14 version:
#   - Lite: profit target 8% -> 12%, max loss 5% -> 3%.
#   - Standard: $20k / $30k tiers retired; $5k / $15k / $25k added.
#     10-day evaluation window REMOVED (challenge_period_days=None).
#   - Payout split: 70% -> 80% (informational; not threshold-based).
#   - Boost: new track with its OWN parameter set — stricter than Standard.
#     Tiers are $10k / $20k / $30k / $50k (note: $20k / $30k exist on Boost
#     even though they were retired on Standard, and $5k / $15k / $25k do
#     NOT exist on Boost).
#     Thresholds: profit_target=12%, max_loss=5%, daily_drawdown=3%,
#     valid_trading_days >= 7, challenge_period_days <= 10 (Boost keeps the
#     10-day deadline that Standard dropped).
_STANDARD_THRESHOLDS = {
    "profit_target_pct": 10, "max_loss_pct": 6, "daily_drawdown_pct": 3,
    "valid_trading_days_required": 7, "challenge_period_days": None,
}
_BOOST_THRESHOLDS = {
    "profit_target_pct": 12, "max_loss_pct": 5, "daily_drawdown_pct": 3,
    "valid_trading_days_required": 7, "challenge_period_days": 10,
}

THRESHOLDS_BY_MODE = {
    "lite": {
        "profit_target_pct": 12,
        "max_loss_pct": 3,
        "daily_drawdown_pct": None,
        "valid_trading_days_required": None,
        "challenge_period_days": None,
    },
    "standard-5k":  dict(_STANDARD_THRESHOLDS),
    "standard-10k": dict(_STANDARD_THRESHOLDS),
    "standard-15k": dict(_STANDARD_THRESHOLDS),
    "standard-25k": dict(_STANDARD_THRESHOLDS),
    "standard-50k": dict(_STANDARD_THRESHOLDS),
    # Boost tiers: $10k / $20k / $30k / $50k only. There is no $5k / $15k /
    # $25k Boost product.
    "boost-10k": dict(_BOOST_THRESHOLDS),
    "boost-20k": dict(_BOOST_THRESHOLDS),
    "boost-30k": dict(_BOOST_THRESHOLDS),
    "boost-50k": dict(_BOOST_THRESHOLDS),
    "payout": {
        "profit_target_pct": None,
        "max_loss_pct": 6, "daily_drawdown_pct": 3,
        "valid_trading_days_required": None,
        "challenge_period_days": None,
    },
}

RULE_REMINDERS = [
    "Minimum holding time per position: 1 minute (less is a violation).",
    "Forbidden: multi-account opening, multi-account hedging, quote-delay exploits, high-frequency cancel/replace.",
    "Leverage caps: Challenge 10X / Payout 20X.",
    "Rate limit: max 5 orders per second per account.",
    "Inactivity: account is suspended after 30 calendar days without a real fill. "
    "Logins, market data, agent connect, placing/cancelling orders, deposits and "
    "auto-liquidations do NOT count as activity — only an executed trade resets the clock.",
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


def main() -> None:
    cfg = load_config()
    mode = cfg.get("mode", "")
    th = THRESHOLDS_BY_MODE.get(mode, {})

    bal_resp = http_request("GET", "/portfolio/balances",
                            query={"exchange_account_id": cfg["exchange_account_id"]}, cfg=cfg)
    balances = bal_resp.get("data", {}).get("balances", [])
    bal = balances[0] if balances else {}
    # total_equity_value already includes unrealized_pnl per the exchange's
    # balance contract (wallet_balance + unrealized_pnl). Use it as the PnL
    # basis; expose the components separately so agents can see the breakdown.
    total_equity = float(bal.get("total_equity_value", 0))
    wallet_balance = float(bal.get("wallet_balance", 0))
    unrealized_pnl = float(bal.get("unrealized_pnl", 0))
    realized_pnl = float(bal.get("realized_pnl", 0))
    initial_balance = cfg.get("initial_balance") or total_equity

    pos_resp = http_request("GET", "/positions",
                            query={"exchange_account_id": cfg["exchange_account_id"]}, cfg=cfg)
    positions = pos_resp.get("data", {}).get("positions", [])
    open_pos_count = len(positions)

    pnl_pct = ((total_equity - initial_balance) / initial_balance * 100) if initial_balance else 0
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

    output = {
        "exchange_account_id": cfg["exchange_account_id"],
        "active_exchange": active_exchange,
        "mode": mode,
        "initial_balance": initial_balance,
        "total_equity_value": total_equity,
        "wallet_balance": wallet_balance,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "current_pnl_pct": round(pnl_pct, 2),
        "profit_target_pct": th.get("profit_target_pct"),
        "thresholds": {
            "max_loss": {
                "limit_pct": th.get("max_loss_pct"),
                "current_pct": round(loss_pct, 2),
                "status": _status(loss_pct, th.get("max_loss_pct")),
            },
            "daily_drawdown": {
                "limit_pct": th.get("daily_drawdown_pct"),
                "note": "Compute from /pnl/closed + intraday balance change; not auto-derived in MVP.",
            },
            "valid_trading_days": {
                "required": th.get("valid_trading_days_required"),
                "note": "Compute by aggregating /trades per day; not auto-derived in MVP.",
            },
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
