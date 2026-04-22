"""Unified query entry.

Subcommands:
  positions         [--symbol]
  balance
  open-orders       [--symbol]          # regular LIMIT/MARKET orders only
  condition-orders  [--symbol]          # STOP_*/TAKE_PROFIT_* trigger orders (TP/SL)
  history-orders    [--symbol] [--page] [--limit]
  trades            [--symbol] [--page] [--limit]
  pnl-closed        [--symbol] [--start <unix-microsec>] [--end <unix-microsec>] [--page] [--limit]
  leverage          --symbol
"""
from __future__ import annotations

import argparse

from _common import http_request, load_config, print_json


def _common_query(cfg, extra: dict | None = None) -> dict:
    q = {"exchange_account_id": cfg["exchange_account_id"]}
    if extra:
        q.update({k: v for k, v in extra.items() if v not in (None, "")})
    return q


def cmd_positions(args, cfg):
    resp = http_request("GET", "/positions", query=_common_query(cfg, {"symbol": args.symbol}), cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_balance(_args, cfg):
    resp = http_request("GET", "/portfolio/balances", query=_common_query(cfg), cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_open_orders(args, cfg):
    resp = http_request("GET", "/openOrders", query=_common_query(cfg, {"symbol": args.symbol}), cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_condition_orders(args, cfg):
    resp = http_request("GET", "/conditionOrders", query=_common_query(cfg, {"symbol": args.symbol}), cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_history_orders(args, cfg):
    resp = http_request("GET", "/historyOrders",
                        query=_common_query(cfg, {"symbol": args.symbol, "page": args.page, "limit": args.limit}),
                        cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_trades(args, cfg):
    resp = http_request("GET", "/trades",
                        query=_common_query(cfg, {"symbol": args.symbol, "page": args.page, "limit": args.limit}),
                        cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_pnl_closed(args, cfg):
    extra = {
        "symbol": args.symbol,
        "start_time": args.start,
        "end_time": args.end,
        "page": args.page,
        "limit": args.limit,
    }
    resp = http_request("GET", "/pnl/closed", query=_common_query(cfg, extra), cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_leverage(args, cfg):
    resp = http_request("GET", "/getLeverage", query=_common_query(cfg, {"symbol": args.symbol}), cfg=cfg)
    print_json(resp.get("data", resp))


def main() -> None:
    p = argparse.ArgumentParser(description="Query endpoints")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("positions"); sp.add_argument("--symbol"); sp.set_defaults(func=cmd_positions)
    sub.add_parser("balance").set_defaults(func=cmd_balance)
    sp = sub.add_parser("open-orders"); sp.add_argument("--symbol"); sp.set_defaults(func=cmd_open_orders)
    sp = sub.add_parser("condition-orders"); sp.add_argument("--symbol"); sp.set_defaults(func=cmd_condition_orders)

    sp = sub.add_parser("history-orders")
    sp.add_argument("--symbol"); sp.add_argument("--page", type=int); sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_history_orders)

    sp = sub.add_parser("trades")
    sp.add_argument("--symbol"); sp.add_argument("--page", type=int); sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_trades)

    sp = sub.add_parser("pnl-closed")
    sp.add_argument("--symbol")
    sp.add_argument("--start", type=int, help="Unix microseconds")
    sp.add_argument("--end", type=int, help="Unix microseconds")
    sp.add_argument("--page", type=int); sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_pnl_closed)

    sp = sub.add_parser("leverage"); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_leverage)

    args = p.parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
