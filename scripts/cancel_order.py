"""POST /cancelOrder (single) or /cancelOrders (batch by symbol).

Single-cancel works for BOTH regular and conditional (STOP_*/TAKE_PROFIT_*)
orders — pass the `order_id` returned when the order was created. For condition
orders, look up the id via `query.py condition-orders` (they do NOT appear under
`query.py open-orders`).

`--all` cancels every non-conditional open order for the symbol. To bulk-cancel
conditional orders, list them with `query.py condition-orders` and cancel each
by id.
"""
from __future__ import annotations

import argparse

from _common import http_request, load_config, print_json


def main() -> None:
    p = argparse.ArgumentParser(description="Cancel an order or all orders for a symbol")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--order-id", help="exchange_order_id (single cancel)")
    g.add_argument("--all", action="store_true", help="Cancel all orders for the given symbol")
    p.add_argument("--symbol", required=True)
    p.add_argument("--trace-id", default="")
    args = p.parse_args()

    cfg = load_config()

    if args.all:
        body = {
            "exchange_account_id": cfg["exchange_account_id"],
            "symbol": args.symbol,
        }
        resp = http_request("POST", "/cancelOrders", json_body=body, cfg=cfg)
    else:
        body = {
            "exchange_account_id": cfg["exchange_account_id"],
            "exchange_order_id": args.order_id,
            "trace_id": args.trace_id or args.order_id,
            "symbol": args.symbol,
        }
        resp = http_request("POST", "/cancelOrder", json_body=body, cfg=cfg)

    print_json(resp.get("data", resp))


if __name__ == "__main__":
    main()
