"""Public market data (no token required, but reuses base_url from config).

Subcommands:
  board                                            full-market ticker
  search   --keyword
  kline    --exchange --symbol --timeframe [--limit]
  orderbook --exchange --symbol
  trades   --exchange --symbol
  contract --exchange --symbol                     contract detail
  metadata                                         all-pair metadata
"""
from __future__ import annotations

import argparse

from _common import http_request, load_config, print_json


def cmd_board(_args, cfg):
    resp = http_request("GET", "/markets/board", cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_search(args, cfg):
    resp = http_request("GET", "/markets/search", query={"keyword": args.keyword}, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_kline(args, cfg):
    q = {"exchange": args.exchange, "symbol": args.symbol, "timeframe": args.timeframe}
    if args.limit:
        q["limit"] = args.limit
    resp = http_request("GET", "/markets/kline", query=q, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_orderbook(args, cfg):
    resp = http_request("GET", "/markets/orderbook",
                        query={"exchange": args.exchange, "symbol": args.symbol}, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_trades(args, cfg):
    resp = http_request("GET", "/markets/trades",
                        query={"exchange": args.exchange, "symbol": args.symbol}, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_contract(args, cfg):
    path = f"/markets/contracts/{args.exchange}/{args.symbol}/summary"
    resp = http_request("GET", path, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_metadata(_args, cfg):
    resp = http_request("GET", "/market/metadata", cfg=cfg)
    print_json(resp.get("data", resp))


def main() -> None:
    p = argparse.ArgumentParser(description="Market data endpoints")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("board").set_defaults(func=cmd_board)

    sp = sub.add_parser("search"); sp.add_argument("--keyword", required=True); sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("kline")
    sp.add_argument("--exchange", required=True)
    sp.add_argument("--symbol", required=True)
    sp.add_argument("--timeframe", required=True, help="1m | 5m | 1h | 1d | ...")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_kline)

    sp = sub.add_parser("orderbook"); sp.add_argument("--exchange", required=True); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_orderbook)
    sp = sub.add_parser("trades"); sp.add_argument("--exchange", required=True); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_trades)
    sp = sub.add_parser("contract"); sp.add_argument("--exchange", required=True); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_contract)

    sub.add_parser("metadata").set_defaults(func=cmd_metadata)

    args = p.parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
