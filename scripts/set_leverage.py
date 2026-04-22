"""POST /setLeverage.

Caps based on config.mode:
  Challenge stage (lite / standard-*): 10X
  Payout stage (payout):               20X
"""
from __future__ import annotations

import argparse

from _common import http_request, load_config, print_json, die


CHALLENGE_MAX_LEVERAGE = 10
PAYOUT_MAX_LEVERAGE = 20


def main() -> None:
    p = argparse.ArgumentParser(description="Set leverage")
    p.add_argument("--symbol", required=True)
    p.add_argument("--leverage", type=int, required=True)
    p.add_argument("--margin-mode", default="CROSS", choices=["CROSS", "ISOLATED"])
    args = p.parse_args()

    cfg = load_config()
    mode = cfg.get("mode", "")
    if mode == "payout":
        max_lev = PAYOUT_MAX_LEVERAGE
        stage = "Payout"
    else:
        max_lev = CHALLENGE_MAX_LEVERAGE
        stage = "Challenge"

    if args.leverage > max_lev:
        die(
            f"Leverage {args.leverage} exceeds the {stage}-stage cap of {max_lev}X.\n"
            f"If you need more, double-check the mode setting (current mode={mode})."
        )

    body = {
        "exchange_account_id": cfg["exchange_account_id"],
        "symbol": args.symbol,
        "leverage": args.leverage,
        "margin_mode": args.margin_mode,
    }
    resp = http_request("POST", "/setLeverage", json_body=body, cfg=cfg)
    print_json(resp.get("data", resp))


if __name__ == "__main__":
    main()
