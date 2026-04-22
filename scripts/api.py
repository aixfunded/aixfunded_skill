"""Generic HTTP caller for endpoints not wrapped by a dedicated script.

Usage:
  python3 api.py GET /positions --query "exchange_account_id=987654321"
  python3 api.py POST /createOrder --json '{"symbol":"BTC-USDC",...}'

WebSocket is out of scope for the MVP; see references/api-websocket.md if needed.
"""
from __future__ import annotations

import argparse
import json
from urllib.parse import parse_qsl

from _common import http_request, load_config, print_json, die


def main() -> None:
    p = argparse.ArgumentParser(description="Generic HTTP fallback caller")
    p.add_argument("method", choices=["GET", "POST", "PUT", "DELETE"])
    p.add_argument("path", help="API path starting with `/`, e.g. /positions")
    p.add_argument("--query", default=None, help='query string, e.g. "a=1&b=2"')
    p.add_argument("--json", dest="json_body", default=None, help="POST body as JSON string")
    p.add_argument("--inject-account", action="store_true",
                   help="Auto-inject config.exchange_account_id into query/body when missing")
    args = p.parse_args()

    cfg = load_config()

    query = dict(parse_qsl(args.query)) if args.query else None

    body = None
    if args.json_body:
        try:
            body = json.loads(args.json_body)
        except json.JSONDecodeError as e:
            die(f"Failed to parse --json: {e}")

    if args.inject_account:
        acct = cfg["exchange_account_id"]
        if query is not None and "exchange_account_id" not in query:
            query["exchange_account_id"] = acct
        if body is not None and "exchange_account_id" not in body:
            body["exchange_account_id"] = acct

    resp = http_request(args.method, args.path, query=query, json_body=body, cfg=cfg)
    print_json(resp)


if __name__ == "__main__":
    main()
