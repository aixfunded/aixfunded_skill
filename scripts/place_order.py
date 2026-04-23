"""POST /createOrder.

- exchange_account_id is auto-injected from config.
- client_order_id auto-generated as agent-{ms}-{uuid8} when not supplied.

Two ways to set TP/SL:
  1. Attach TP/SL while opening: pass --tp-price / --sl-price on the open order.
  2. Standalone conditional order: --order-type STOP_MARKET or TAKE_PROFIT_MARKET
     with --trigger-price and --reduce-only.

Use `query.py condition-orders` to list pending TP/SL (they do NOT show under
open-orders).

AI reasoning (required for agent-mode accounts):
  Pass --reasoning "<text>" with the agent's rationale for this order. The
  server REQUIRES this field on agent-mode accounts — omitting it returns
  INVALID_ARGUMENT. Max 4096 bytes (UTF-8), over-limit is rejected by the
  server (also enforced client-side, no silent truncation).

  Sampled reasoning is LLM-graded; baseline 60, LLM adds +/-40, must stay
  >= 60 to pass. Templated / repeated text is penalised -5 to -20 each.
"""
from __future__ import annotations

import argparse
import time
import uuid
from datetime import datetime, timezone

from _common import (
    die,
    http_request,
    load_config,
    load_state,
    print_json,
    save_state,
    server_utc_ts_from_headers,
)

# Server contract: reasoning is required on agent-mode accounts and
# capped at 4096 bytes (UTF-8). Over-limit returns INVALID_ARGUMENT.
REASONING_MAX_BYTES = 4096


def main() -> None:
    p = argparse.ArgumentParser(description="Place an order")
    p.add_argument("--symbol", required=True, help="e.g. BTC-USDC")
    p.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p.add_argument("--order-type", required=True,
                   choices=["LIMIT", "MARKET", "STOP_LIMIT", "STOP_MARKET",
                            "TAKE_PROFIT_LIMIT", "TAKE_PROFIT_MARKET"])
    p.add_argument("--size", required=True, help="Quantity (string)")
    p.add_argument("--price", default="", help="Price (required for LIMIT)")
    p.add_argument("--tif", default=None, choices=[None, "GTC", "FOK", "IOC", "POST_ONLY"])
    p.add_argument("--reduce-only", action="store_true")
    p.add_argument("--client-order-id", default=None)
    p.add_argument("--trigger-price", default="")
    p.add_argument("--trigger-type", default="", choices=["", "ORACLE", "INDEX", "MARKET", "MARK"])
    # Attach TP / SL to this (opening) order. Ignored for pure trigger orders.
    p.add_argument("--tp-price", default="", help="Take-profit trigger price attached to this open order")
    p.add_argument("--sl-price", default="", help="Stop-loss trigger price attached to this open order")
    p.add_argument("--tpsl-trigger-type", default="MARK",
                   choices=["ORACLE", "INDEX", "MARKET", "MARK"],
                   help="Trigger reference for attached TP/SL (default MARK)")
    p.add_argument("--reasoning", default="",
                   help="REQUIRED for agent-mode accounts: rationale for this order. "
                        "Max 4096 bytes (UTF-8). Over-limit / missing returns "
                        "INVALID_ARGUMENT from the server.")
    args = p.parse_args()

    # Enforce the server's contract client-side: required and <= 4096 bytes UTF-8.
    # Failing fast with a clear message is better than letting the server say
    # INVALID_ARGUMENT with no hint about what went wrong.
    reasoning_text = (args.reasoning or "").strip()
    if not reasoning_text:
        die(
            "--reasoning is required for agent-mode accounts. Pass a fresh, "
            "order-specific rationale (what you're trading, why, how big, and "
            "where you'll exit). See SKILL.md / references/risk-rules.md for "
            "the scoring rules."
        )
    reasoning_bytes = len(reasoning_text.encode("utf-8"))
    if reasoning_bytes > REASONING_MAX_BYTES:
        die(
            f"--reasoning is {reasoning_bytes} bytes (UTF-8); limit is "
            f"{REASONING_MAX_BYTES}. Shorten it and retry."
        )

    cfg = load_config()

    cid = args.client_order_id or f"agent-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    tp_attached = bool(args.tp_price)
    sl_attached = bool(args.sl_price)
    body = {
        "exchange_account_id": cfg["exchange_account_id"],
        "client_order_id": cid,
        "symbol": args.symbol,
        "side": args.side,
        "size": args.size,
        "price": args.price,
        "order_type": args.order_type,
        "time_in_force": args.tif or ("GTC" if args.order_type == "LIMIT" else ""),
        "reduce_only": args.reduce_only,
        "trigger_price": args.trigger_price,
        "trigger_type": args.trigger_type,
        "is_position_tpsl": False,
        "is_open_tpsl_order": tp_attached or sl_attached,
        "is_set_open_tp": tp_attached,
        "is_set_open_sl": sl_attached,
        "tp_trigger_price": args.tp_price,
        "tp_trigger_price_type": args.tpsl_trigger_type if tp_attached else "",
        "sl_trigger_price": args.sl_price,
        "sl_trigger_price_type": args.tpsl_trigger_type if sl_attached else "",
    }
    if reasoning_text:
        body["reasoning"] = reasoning_text
    resp, response_headers = http_request(
        "POST", "/createOrder", json_body=body, cfg=cfg, return_headers=True
    )

    # Challenge period starts at the first successful order placement.
    # Stamp once in state.json using the server's Date header (falls back to
    # local UTC clock on parse failure).
    state = load_state()
    if not state.get("challenge_start_ts"):
        ts = server_utc_ts_from_headers(response_headers)
        state["challenge_start_ts"] = ts
        state["challenge_start_date_utc"] = (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        save_state(state)

    print_json(resp.get("data", resp))


if __name__ == "__main__":
    main()
