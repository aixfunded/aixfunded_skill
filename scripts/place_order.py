"""POST /createOrder.

- exchange_account_id is auto-injected from config.
- client_order_id auto-generated as agent-{ms}-{uuid8} when not supplied.

Two ways to set TP/SL:
  1. Attach TP/SL while opening: pass --tp-price / --sl-price on the open order.
  2. Standalone conditional order: --order-type STOP_MARKET or TAKE_PROFIT_MARKET
     with --trigger-price and --reduce-only.

Use `query.py condition-orders` to list pending TP/SL (they do NOT show under
open-orders).

AI reasoning (agent-mode challenges):
  Pass --reasoning "<markdown-like text>" to attach the agent's rationale for
  this order. The server samples reasoning and grades it via LLM; an average
  score < 60 marks the agent invalid and fails the challenge. Max 1000 chars
  (truncated server-side). Skipping it on an agent-run challenge risks missing
  the bar; templated / repeated text is penalised -5~20 per instance.
"""
from __future__ import annotations

import argparse
import time
import uuid
from datetime import datetime, timezone

from _common import (
    http_request,
    load_config,
    load_state,
    print_json,
    save_state,
    server_utc_ts_from_headers,
)


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
                   help="Agent's rationale for this order (max 1000 chars, truncated "
                        "server-side). LLM-graded; avg < 60 fails the challenge.")
    args = p.parse_args()

    # Enforce the 1000-char ceiling client-side so we fail loud before the
    # server silently truncates.
    reasoning_text = (args.reasoning or "").strip()
    if len(reasoning_text) > 1000:
        reasoning_text = reasoning_text[:1000]

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
