"""Close an existing position with a market reduce-only order.

- Queries /positions for the given symbol (or all if --all), derives side + size,
  and sends the opposite-side MARKET reduce-only order.
- Respects the 1-minute minimum holding time rule: refuses to close a position
  opened less than 60 seconds ago unless --force is passed.
"""
from __future__ import annotations

import argparse
import time
import uuid

from _common import die, http_request, load_config, print_json


MIN_HOLD_SECONDS = 60


def fetch_positions(cfg, symbol: str | None) -> list[dict]:
    q = {"exchange_account_id": cfg["exchange_account_id"]}
    if symbol:
        q["symbol"] = symbol
    resp = http_request("GET", "/positions", query=q, cfg=cfg)
    data = resp.get("data", resp)
    positions = data.get("positions") if isinstance(data, dict) else []
    return [p for p in (positions or []) if float(p.get("quantity", 0) or 0) > 0]


def close_one(cfg, pos: dict, force: bool, reasoning: str) -> dict:
    side = "SELL" if pos["side"].upper() == "LONG" else "BUY"
    size = pos["quantity"]
    symbol = pos["symbol"]

    opened_at_us = pos.get("created_at") or pos.get("opened_at") or 0
    if opened_at_us and not force:
        held_s = time.time() - (int(opened_at_us) / 1_000_000)
        if held_s < MIN_HOLD_SECONDS:
            die(
                f"Position on {symbol} has been held for only {held_s:.1f}s. "
                f"Minimum is {MIN_HOLD_SECONDS}s per challenge rules. "
                f"Wait {MIN_HOLD_SECONDS - held_s:.0f}s or pass --force to override."
            )

    body = {
        "exchange_account_id": cfg["exchange_account_id"],
        "client_order_id": f"agent-close-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
        "symbol": symbol,
        "side": side,
        "size": size,
        "price": "",
        "order_type": "MARKET",
        "time_in_force": "",
        "reduce_only": True,
        "trigger_price": "",
        "trigger_type": "",
        "is_position_tpsl": False,
        "is_open_tpsl_order": False,
        "is_set_open_tp": False,
        "is_set_open_sl": False,
        "tp_trigger_price": "",
        "tp_trigger_price_type": "",
        "sl_trigger_price": "",
        "sl_trigger_price_type": "",
        "reasoning": reasoning,
    }
    resp = http_request("POST", "/createOrder", json_body=body, cfg=cfg)
    return {"symbol": symbol, "side": side, "size": size, "result": resp.get("data", resp)}


def main() -> None:
    p = argparse.ArgumentParser(description="Close position(s) via market reduce-only order")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--symbol", help="Close the position for this symbol")
    g.add_argument("--all", action="store_true", help="Close every open position")
    p.add_argument("--force", action="store_true",
                   help="Skip the 1-minute minimum-hold guard (risk of violation)")
    p.add_argument("--reasoning", required=True,
                   help="REQUIRED: rationale for this close (agent-mode accounts). "
                        "Max 4096 bytes (UTF-8). Make it order-specific.")
    args = p.parse_args()

    reasoning_text = (args.reasoning or "").strip()
    if not reasoning_text:
        die("--reasoning is required for agent-mode accounts.")
    if len(reasoning_text.encode("utf-8")) > 4096:
        die("--reasoning exceeds 4096 bytes (UTF-8). Shorten it and retry.")

    cfg = load_config()
    positions = fetch_positions(cfg, None if args.all else args.symbol)
    if not positions:
        die("No open position to close." if args.symbol else "No open positions.")

    results = [close_one(cfg, pos, args.force, reasoning_text) for pos in positions]
    print_json(results if len(results) > 1 else results[0])


if __name__ == "__main__":
    main()
