# AiXFund Trading Skill - Scripts

Python 3.9+. No third-party dependencies (stdlib `urllib` only).

## Storage layout

Credentials and runtime state live in separate files:

- `~/.aixfund/accounts/<account_id>.json` — credentials only:
  ```json
  {
    "token": "af_...",
    "exchange_account_id": "987654321",
    "base_url_http": "http://<AIXFUND_HOST>:8088/api/v1",
    "base_url_ws_private": "ws://<AIXFUND_HOST>:8087/realtime_private",
    "base_url_ws_public": "ws://<AIXFUND_HOST>:8086/realtime_public"
  }
  ```
  Written by the STEP 2 terminal snippet (one file per account, the user can
  have many).

- `<skill-root>/state.json` — per-skill runtime state (what's bound, mode,
  challenge clock):
  ```json
  {
    "active_account_id": "987654321",
    "mode": "standard-10k",
    "initial_balance": 10000,
    "challenge_start_ts": 1776834885,
    "challenge_start_date_utc": "2026-04-22"
  }
  ```
  `challenge_start_ts` (UTC seconds) is stamped automatically by
  `place_order.py` at the user's first successful order placement, using the
  server `Date` response header. Never set it manually.

One skill install = one bound account. To operate two accounts in parallel,
install the skill twice.

## First-time setup (recommended — keeps the token out of the AI agent)

1. Visit https://aixfunded.com/app/agent-api and paste the terminal snippet
   into your terminal. It writes credentials to
   `~/.aixfund/accounts/<account_id>.json`.
2. Ask your AI agent: *"Initialize challenge, account_id: <id>"*. The agent runs:
   ```bash
   python3 config.py bind --account-id <id>
   ```
   which calls `/exchange-accounts` to infer `mode` and `initial_balance` and
   writes `state.json`. Same command is used to switch accounts later —
   just change the id.

## Legacy (token passes through the AI)

```bash
python3 config.py bootstrap --token "af_..."
# multi-account? pass --exchange-account-id <id>
```

## Command cheatsheet

| Purpose | Command |
| --- | --- |
| Show current binding | `python3 config.py show` |
| List available accounts | `python3 config.py list-accounts` |
| Bind / switch account | `python3 config.py bind --account-id <id>` |
| Reset challenge clock | `python3 config.py reset-challenge` |
| Migrate legacy config | `python3 config.py migrate` |
| Validate token | `python3 auth_check.py` |
| Place order | `python3 place_order.py --symbol BTC-USDT --side BUY --order-type LIMIT --size 0.1 --price 60000` |
| Open with attached TP/SL | `python3 place_order.py --symbol BTC-USDT --side BUY --order-type MARKET --size 0.001 --tp-price 80000 --sl-price 75000` |
| Standalone TP trigger | `python3 place_order.py --symbol BTC-USDT --side SELL --order-type TAKE_PROFIT_MARKET --size 0.001 --trigger-price 80000 --trigger-type MARK --reduce-only` |
| Close position | `python3 close_position.py --symbol BTC-USDT` / `--all` |
| Cancel one order | `python3 cancel_order.py --order-id 123 --symbol BTC-USDT` (works for both regular & conditional) |
| Cancel all (by symbol) | `python3 cancel_order.py --all --symbol BTC-USDT` (non-conditional only) |
| Set leverage | `python3 set_leverage.py --symbol BTC-USDT --leverage 5` |
| Positions | `python3 query.py positions [--symbol ...]` |
| Balance | `python3 query.py balance` |
| Open orders | `python3 query.py open-orders` (regular only) |
| Condition orders | `python3 query.py condition-orders` (TP/SL/STOP trigger orders) |
| History orders | `python3 query.py history-orders [--symbol ...] [--page 1] [--limit 20]` |
| Trades | `python3 query.py trades` |
| Closed PnL | `python3 query.py pnl-closed` |
| Market board | `python3 markets.py board` |
| Kline | `python3 markets.py kline --exchange apex --symbol BTC-USDC --timeframe 1m --limit 100` |
| Orderbook | `python3 markets.py orderbook --exchange apex --symbol BTC-USDC` |
| Risk snapshot | `python3 risk_status.py` |
| Generic fallback | `python3 api.py GET /xxx [--query "a=1"]` or `POST /xxx --json '{...}'` |

## Failure fallback

If a dedicated script fails, fall back in this order:

1. Use the generic caller: `python3 api.py <METHOD> <PATH>`.
2. If that fails too, use curl from the examples in `../references/api-http.md`. The token lives in `~/.aixfund/config.json`:

```bash
TOKEN=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.aixfund/config.json")))["token"])')
ACCT=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.aixfund/config.json")))["exchange_account_id"])')
curl -X POST http://<AIXFUND_HOST>:8088/api/v1/createOrder \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exchange_account_id":"'$ACCT'","client_order_id":"agent-test-001","symbol":"BTC-USDC","side":"BUY","size":"0.1","price":"60000","order_type":"LIMIT","time_in_force":"GTC"}'
```

## Conventions

- Output: success -> JSON to stdout; failure -> stderr + non-zero exit code.
- Money fields are strings (per propdesk docs).
- Timestamps are int64 microseconds.
- HTTP errors map to friendly hints (401 -> token invalid, 403 -> permission, 429 -> rate limit).
