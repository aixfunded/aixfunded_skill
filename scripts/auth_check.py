"""GET /exchange-accounts: validate the token and list authorized accounts.

Output JSON: {"valid": true, "current_exchange_account_id": ..., "accounts": [...]}
"""
from __future__ import annotations

from _common import http_request, print_json, load_config


def main() -> None:
    cfg = load_config()
    resp = http_request("GET", "/exchange-accounts", cfg=cfg)
    accounts = resp.get("data", {}).get("exchange_accounts", [])
    print_json({
        "valid": True,
        "current_exchange_account_id": cfg.get("exchange_account_id"),
        "accounts": accounts,
    })


if __name__ == "__main__":
    main()
