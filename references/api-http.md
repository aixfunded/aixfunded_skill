# HTTP API reference

> Base URL (production): `http://<AIXFUND_HOST>/api/v1`
> Full spec: project root `aixfund-integration-http-ws.md`. This file is the agent quick-ref + curl fallback.

## Common

### Authentication

Every Private endpoint (everything except `/markets/*`) requires:

```
Authorization: Bearer <token>
```

The token lives in `~/.aixfund/config.json`. To extract it:

```bash
TOKEN=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.aixfund/config.json")))["token"])')
ACCT=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.aixfund/config.json")))["exchange_account_id"])')
BASE=http://<AIXFUND_HOST>/api/v1
```

### Response envelope

Success: `{"code": 0, "msg": "ok", "data": {...}}`
Failure: `{"code": <business code>, "msg": "..."}`

### Error codes

| HTTP | Code | Meaning |
| --- | --- | --- |
| 400 | 10001 | Invalid parameters |
| 401 | 10002 | Authentication failed |
| 403 | 10003 | Permission denied |
| 404 | 10004 | Resource not found |
| 500 | 10005 | Internal server error |
| 409 | 10006 | Resource already exists |
| 400 | 10007 | Precondition failed |
| 429 | 10008 | Too many requests (5/s rate limit) |

---

## Trading (Private)

### POST /createOrder

```bash
curl -X POST $BASE/createOrder \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "exchange_account_id": "'$ACCT'",
    "client_order_id": "agent-'$(date +%s%N | cut -c1-13)'",
    "symbol": "BTC-USDT",
    "side": "BUY",
    "size": "0.1",
    "price": "60000",
    "order_type": "LIMIT",
    "time_in_force": "GTC",
    "reduce_only": false,
    "trigger_price": "",
    "trigger_type": "",
    "is_position_tpsl": false,
    "is_open_tpsl_order": false,
    "is_set_open_tp": false,
    "is_set_open_sl": false,
    "tp_trigger_price": "",
    "tp_trigger_price_type": "",
    "sl_trigger_price": "",
    "sl_trigger_price_type": ""
  }'
```

Required vs optional:
- Required: `exchange_account_id`, `client_order_id` (idempotent), `symbol`, `side` (BUY|SELL), `order_type` (LIMIT|MARKET|STOP_LIMIT|STOP_MARKET|TAKE_PROFIT_LIMIT|TAKE_PROFIT_MARKET).
- Often required: `size`, `price` (LIMIT must have price > 0).
- Optional: `time_in_force` (GTC|FOK|IOC|POST_ONLY), `reduce_only`, `trigger_price`, `trigger_type` (INDEX|MARKET|MARK; `ORACLE` not supported for attached TP/SL).
- Attached TP/SL (when `is_open_tpsl_order=true`):
  - At least one of `is_set_open_tp` / `is_set_open_sl` must be `true`.
  - Whichever leg is enabled must have its `*_trigger_price > 0` and a valid `*_trigger_price_type` (`MARKET` / `MARK` / `INDEX`).
  - Both legs are managed as an OCO pair: when one triggers the other auto-cancels.
- **Required for agent-mode accounts**: `reasoning` — plain string, the
  agent's rationale for this order. Max **4096 bytes** (UTF-8). Missing on
  an agent-mode account or over-limit returns `INVALID_ARGUMENT`. Manual
  accounts reject API-placed orders entirely (must go through the AiXFund
  front-end). A sampled subset is LLM-graded; an average score < 60 fails
  the challenge (see "AI reasoning score" below).

### AI reasoning score (agent-mode accounts)

The platform samples and grades `reasoning` via LLM. Every challenge starts
at 60 points; LLM judgement adds ±40. Score < 60 fails the challenge
(agent flagged invalid). Duplicate / templated reasoning is penalised
−5 to −20 per instance.

High-quality example:
```json
{
  "reasoning": "BTC 4H breaks prior high at $68,500; volume expanding and MACD golden cross suggest trend continuation. Sizing at 5% of equity; exit below the breakout level to contain false-breakout risk."
}
```

Low-quality (will be penalised):
```json
{"reasoning": "continue buy"}   // templated, repeated across orders
{"reasoning": "ok"}              // no substance
```
Missing `reasoning` on an agent-mode account is rejected outright by the
server with `INVALID_ARGUMENT` (not just a score penalty).

Guidance:
- Always pass `reasoning` on agent-mode accounts — it's required.
- Reference the actual setup: indicators / price levels / position sizing / contingency plan.
- Never reuse the same text across orders; make each rationale order-specific.
- Keep under 4096 bytes UTF-8 (Chinese counts ~3 bytes per character).

Response:
```json
{"code":0,"msg":"ok","data":{"order_id":"1234","exchange_order_id":"1234","status":"PENDING"}}
```

### POST /cancelOrder

```bash
curl -X POST $BASE/cancelOrder \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exchange_account_id":"'$ACCT'","exchange_order_id":"1234567890","trace_id":"trace-001","symbol":"BTC-USDT"}'
```

### POST /cancelOrders (batch by symbol)

```bash
curl -X POST $BASE/cancelOrders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exchange_account_id":"'$ACCT'","symbol":"BTC-USDT"}'
```

### POST /setLeverage

```bash
curl -X POST $BASE/setLeverage \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"exchange_account_id":"'$ACCT'","symbol":"BTC-USDT","leverage":5,"margin_mode":"CROSS"}'
```

> Caps: Challenge 10X / Payout 5X.

---

## Queries (Private)

### GET /positions

```bash
curl "$BASE/positions?exchange_account_id=$ACCT&symbol=BTC-USDT" \
  -H "Authorization: Bearer $TOKEN"
```

### GET /portfolio/balances

```bash
curl "$BASE/portfolio/balances?exchange_account_id=$ACCT" \
  -H "Authorization: Bearer $TOKEN"
```

### GET /openOrders

```bash
curl "$BASE/openOrders?exchange_account_id=$ACCT" \
  -H "Authorization: Bearer $TOKEN"
```

Each entry order in the response carries two arrays — **always present**, possibly empty — that embed the attached TP / SL legs (only `PENDING` ones):

```json
{
  "order_id": "<entry_id>",
  "side": "BUY",
  "status": "OPEN",
  "take_profit": [
    {"order_id": "<tp_id>", "order_type": "MARKET", "trigger_price": "90000", "trigger_type": "MARK", "size": "0.001", "create_at": 1778251232458}
  ],
  "stop_loss": [
    {"order_id": "<sl_id>", "order_type": "MARKET", "trigger_price": "60000", "trigger_type": "MARK", "size": "0.001", "create_at": 1778251232467}
  ]
}
```

- `take_profit[].order_id` / `stop_loss[].order_id` are `condition_order_id`s — pass them straight to `/cancelOrder`.
- Once the entry order is `FILLED` it leaves `/openOrders`; from then on look up the TP/SL via `/conditionOrders`.
- Triggered (`TRIGGERED`) and cancelled (`CANCELED`) legs are not embedded — query `/conditionOrders` for history.
- Standalone trigger orders (`order_type=STOP_*` / `TAKE_PROFIT_*`) are never embedded; they only show under `/conditionOrders`.

### GET /historyOrders

```bash
curl "$BASE/historyOrders?exchange_account_id=$ACCT&page=1&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

### GET /trades

```bash
curl "$BASE/trades?exchange_account_id=$ACCT&page=1&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

### GET /pnl/closed

```bash
curl "$BASE/pnl/closed?exchange_account_id=$ACCT&start_time=1712534400000000&end_time=1712620800000000" \
  -H "Authorization: Bearer $TOKEN"
```

### GET /exchange-accounts

```bash
curl $BASE/exchange-accounts -H "Authorization: Bearer $TOKEN"
```

### GET /getLeverage

```bash
curl "$BASE/getLeverage?exchange_account_id=$ACCT" -H "Authorization: Bearer $TOKEN"
```

### GET /conditionOrders

```bash
curl "$BASE/conditionOrders?exchange_account_id=$ACCT" -H "Authorization: Bearer $TOKEN"
```

---

## Market data (Public, no auth)

### GET /markets/board

```bash
curl $BASE/markets/board
```

### GET /markets/search

```bash
curl "$BASE/markets/search?keyword=BTC"
```

Note on the `exchange` parameter (post 2026-05-15): the backend selects the
"active exchange" at runtime via Nacos and currently returns `binance`
(previously `apex`). All `/markets/*` query endpoints below tolerate a stale
name (e.g. `exchange=apex`) and silently map it to the active hub, but the
response's `exchange` field will always be the active name. The cleanest
flow is to call `GET /market/metadata` first and use `data.active_exchange`
for subsequent calls.

### GET /markets/kline

```bash
# Substitute $EXCH with data.active_exchange from /market/metadata.
EXCH=$(curl -s "$BASE/market/metadata" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["active_exchange"])')
curl "$BASE/markets/kline?exchange=$EXCH&symbol=BTC-USDT&timeframe=1m&limit=100"
```

### GET /markets/orderbook

```bash
curl "$BASE/markets/orderbook?exchange=$EXCH&symbol=BTC-USDT"
```

### GET /markets/trades

```bash
curl "$BASE/markets/trades?exchange=$EXCH&symbol=BTC-USDT"
```

### GET /markets/contracts/{exchange}/{symbol}/summary

```bash
curl "$BASE/markets/contracts/$EXCH/BTC-USDT/summary"
```

### GET /market/metadata

```bash
curl $BASE/market/metadata
# Top-level data.active_exchange tells you the current active venue.
# Use it as the value for all `exchange=` params and as the {exchange} path
# segment in /markets/contracts/{exchange}/{symbol}/summary.
```
