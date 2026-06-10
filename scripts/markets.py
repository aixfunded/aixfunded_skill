"""Public market data (no token required, but reuses base_url from config).

Subcommands:
  board                                            full-market ticker
  search   --keyword
  kline    [--exchange] --symbol --interval [--limit]
  orderbook [--exchange] --symbol
  trades   [--exchange] --symbol
  contract [--exchange] --symbol                   contract detail
  metadata                                         all-pair metadata (incl. active_exchange)

Since the 2026-05-15 backend upgrade the "active exchange" is chosen at
runtime by the server (currently `binance`, previously `apex`). When
`--exchange` is omitted these subcommands fetch `/market/metadata` once and
use `active_exchange`, so the skill keeps working across future swaps. The
backend is also tolerant of stale names (`exchange=apex` is silently mapped
to the active hub), but prefer the active name to keep responses readable.
"""
from __future__ import annotations

import argparse

from _common import die, get_active_exchange, http_request, load_config, print_json


def _resolve_exchange(args, cfg) -> str:
    if args.exchange:
        return args.exchange
    active = get_active_exchange(cfg=cfg)
    if not active:
        die("Could not resolve active_exchange from /market/metadata; pass --exchange explicitly.")
    return active


def cmd_board(_args, cfg):
    resp = http_request("GET", "/markets/board", cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_search(args, cfg):
    resp = http_request("GET", "/markets/search", query={"keyword": args.keyword}, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_kline(args, cfg):
    exch = _resolve_exchange(args, cfg)
    q = {"exchange": exch, "symbol": args.symbol, "interval": args.interval}
    if args.limit:
        q["limit"] = args.limit
    resp = http_request("GET", "/markets/kline", query=q, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_orderbook(args, cfg):
    exch = _resolve_exchange(args, cfg)
    resp = http_request("GET", "/markets/orderbook",
                        query={"exchange": exch, "symbol": args.symbol}, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_trades(args, cfg):
    exch = _resolve_exchange(args, cfg)
    resp = http_request("GET", "/markets/trades",
                        query={"exchange": exch, "symbol": args.symbol}, cfg=cfg)
    print_json(resp.get("data", resp))


def cmd_contract(args, cfg):
    exch = _resolve_exchange(args, cfg)
    path = f"/markets/contracts/{exch}/{args.symbol}/summary"
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
    sp.add_argument("--exchange", default=None,
                    help="Exchange name; default = active_exchange from /market/metadata.")
    sp.add_argument("--symbol", required=True)
    sp.add_argument("--interval", required=True,
                    help="1m | 3m | 5m | 15m | 30m | 1h | 2h | 4h | 6h | 8h | 12h | 1d | 3d | 1w | 1M")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_kline)

    sp = sub.add_parser("orderbook"); sp.add_argument("--exchange", default=None); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_orderbook)
    sp = sub.add_parser("trades"); sp.add_argument("--exchange", default=None); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_trades)
    sp = sub.add_parser("contract"); sp.add_argument("--exchange", default=None); sp.add_argument("--symbol", required=True); sp.set_defaults(func=cmd_contract)

    sub.add_parser("metadata").set_defaults(func=cmd_metadata)

    args = p.parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
