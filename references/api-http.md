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

- `trace_id` is **required** (sent through to trading-server as `x-trace-id`).
- `exchange_order_id` can also be a `condition_order_id` — the gateway falls back to the condition-order cancel path if the regular lookup misses.
- Response shape: `data.order.{order_id, exchange_order_id, status}`. `exchange_order_id` is always `""` (paper venue has no separate exchange-side id); `status` is `"CANCELED"` on the condition-order fallback path.

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

> Caps: Challenge 10X / Payout 5X. Ordering above the cap is rejected with an
> error. (`max_leverage` may show `20` on Payout; ignore it — the cap is 5X.)

---

## Queries (Private)

### GET /positions

```bash
curl "$BASE/positions?exchange_account_id=$ACCT&symbol=BTC-USDT" \
  -H "Authorization: Bearer $TOKEN"
```

- `funding_fee`: this position's **cumulative settled funding-fee total** (sum of settled `paper_funding_records` since the position's `created_at`). **Positive = paid by the user, negative = received by the user** (same sign convention as `/pnl/closed`). Returns `"0"` when there are no records.

### GET /portfolio/balances

```bash
curl "$BASE/portfolio/balances?exchange_account_id=$ACCT" \
  -H "Authorization: Bearer $TOKEN"
```

Key response fields:

| Field | Notes |
| --- | --- |
| `total_equity_value` | `wallet_balance + unrealized_pnl` — the live equity (includes floating PnL). Use this for the "account equity" display; same basis as risk-server's `current_equity`. |
| `wallet_balance` | Realised portion = `initial_capital + realized_pnl − cumulative_fee + cumulative_funding`. |
| `available_balance` | `wallet_balance − initial_margin − frozen_for_orders`; the headroom for new orders. |
| `initial_margin` | Margin already locked by open positions. |
| `maintenance_margin` | Tier-based maintenance margin sum; breaching this triggers liquidation. |
| `frozen_for_orders` | Margin pre-frozen by OPEN LIMIT orders (reduce-only orders don't freeze). Released on cancel / reject / fill. |
| `unrealized_pnl` | Floating PnL by `mark_price`. |
| `realized_pnl` | **Gross** realised PnL — does NOT subtract fees / funding. |
| `realized_pnl_net` | **Net** realised PnL = `realized_pnl − cumulative_fee + cumulative_funding`. Use this for "realised PnL" cards. |
| `cumulative_fee` | Lifetime fees paid (open + close). |
| `cumulative_funding` | Lifetime funding settled. **Positive = paid by user, negative = received** (same sign convention as `/positions.funding_fee` and `/pnl/closed.funding_fee`). |

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

- `execution_type`: currently fixed at `"Trade"`; will return the real value once Maker/Taker distinction is supported.

### GET /trades

```bash
curl "$BASE/trades?exchange_account_id=$ACCT&page=1&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

- `execution_type`: currently fixed at `"Trade"`; will return the real value once Maker/Taker distinction is supported.

### GET /pnl/closed

```bash
curl "$BASE/pnl/closed?exchange_account_id=$ACCT&start_time=1712534400000000&end_time=1712620800000000" \
  -H "Authorization: Bearer $TOKEN"
```

- `side`: **opening direction** — `"BUY"` = LONG / `"SELL"` = SHORT (the entry order's side).
- `leverage` (int): the **historical leverage at the moment of closing** (snapshot written at close, after any tier-based auto step-down) — NOT the account's current `leverage` setting; a later `setLeverage` does not change this value. Historical fills from before this field existed fall back to the current `leverage_settings` value, so the field **never returns 0**.

### GET /exchange-accounts

```bash
curl $BASE/exchange-accounts -H "Authorization: Bearer $TOKEN"
```

Each account carries a `risk` sub-object with the assessment / risk-control data. Key fields:

| Field | Notes |
| --- | --- |
| `status` | `"active"` (running) / `"disabled"` (breached, not recoverable) |
| `alerted` | Whether the alert threshold has been crossed |
| `max_drawdown_pct` | Max-cumulative-loss red line (percent); the threshold for `max_cumulative_loss_pct` |
| `alert_drawdown_pct` | Alert threshold (percent); also against `max_cumulative_loss_pct` |
| `max_daily_drawdown_pct` | Daily-drawdown threshold (percent) |
| `current_equity` | Current equity (live balance + unrealized PnL) |
| `baseline_equity` | Baseline equity (= `initial_capital`) |
| `peak_equity` | Historical peak equity |
| `trough_equity` | Historical trough equity (real-time low including floating loss) |
| `current_loss` | Current instantaneous cumulative loss (USDT) = `max(0, baseline − current)`; `"0"` when in profit |
| `max_cumulative_loss_pct` | **Max cumulative loss rate** (percent) = `(baseline − min(trough, current)) / baseline × 100`. **Same basis as `max_drawdown_pct` / `alert_drawdown_pct` — directly comparable.** `"0"` while the account is in profit. **The "max loss control" card MUST use this field.** |
| `current_drawdown_pct` | **Drawdown from the historical peak** (percent) = `(peak − current) / peak × 100`. ⚠️ This is the pullback relative to `peak_equity`, **NOT** cumulative loss: an account that profited first then pulled back inflates this value even without a real loss. **NOT directly comparable to the `max_drawdown_pct` red line.** |
| `last_daily_drawdown_pct` | **Previous-day drawdown rate** (percent), the value the daily_drawdown worker persists once per day at 08:00 UTC. Always ≤ 0. **Same basis as `max_daily_drawdown_pct` — directly comparable** (breach: `last < -max`). `"0"` = flat / in profit / first day or worker not yet run. ⚠️ 24h discrete sample, refreshed only at 08:00 UTC, NOT an intraday real-time value. |
| `short_hold_count_7d` | int. Rolling 7×24h count of `min_holding_time` rule events (alerts + breaches). `0` = clean. **First event = 1 (alert), second+ = 2+ (BREACH → account REVOKED).** Live since 2026-06-06; before this date the rule existed but was advisory only. |

> Render the "max loss control" card with `max_cumulative_loss_pct`, NOT `current_drawdown_pct`.

### GET /exchange-accounts/:id/challenge

Returns one exchange account's **full assessment progress** in a single call: merges the aixfund business status + equity + risk-control data (three sources combined). Use this for the agent / front-end "challenge progress" card instead of separately hitting aixfund and `/exchange-accounts`.

```bash
# NOTE: account id is a PATH parameter (:id), NOT a ?exchange_account_id= query param.
curl "$BASE/exchange-accounts/$ACCT/challenge" -H "Authorization: Bearer $TOKEN"
```

- **Auth**: Bearer token; `:id` must be ∈ the token's `allowed_account_ids`, otherwise 403.
- ⚠️ **This is the only endpoint where the account id is a path parameter** (`:id`), unlike every other endpoint which takes `?exchange_account_id=`.

Response (`200 OK`):

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "exchange_account_id": "123456789",
    "aixfund": {
      "account_phase": "challenge",
      "trading_mode": "agent",
      "is_agent": true,
      "is_challenge": true,
      "program_id": "standard_5k",
      "status": "active",
      "agent_llm_score": "72.5",
      "agent_llm_score_at_ms": 1780560000000,
      "assessment_start_at_ms": 1780453800000,
      "last_effective_trade_at_ms": 1780557300000,
      "profit_target_pct": "12",
      "min_trading_days": 7,
      "effective_trading_days_so_far": 1
    },
    "equity": {
      "initial_capital": "5000",
      "baseline_equity": "5000",
      "current_equity": "5631.45",
      "current_profit": "631.45",
      "current_profit_pct": "12.629"
    },
    "risk": {
      "max_drawdown_pct": "5",
      "current_drawdown_pct": "0.35",
      "max_daily_drawdown_pct": "3",
      "last_daily_drawdown_pct": "0",
      "max_cumulative_loss_pct": "0",
      "min_holding_seconds": 60,
      "short_hold_count_7d": 0
    }
  }
}
```

`aixfund` sub-object (from the aixfund `Verify` response's `account_challenges[exchange_account_id == :id]`):

| Field | Type | Notes |
| --- | --- | --- |
| `account_phase` | string | `"challenge"` / `"payout"` |
| `trading_mode` | string | `"manual"` / `"agent"` |
| `is_agent` | bool | Convenience for `trading_mode == "agent"` |
| `is_challenge` | bool | Convenience for `account_phase == "challenge"` |
| `program_id` | string | Program ID, e.g. `"standard_5k"` / `"boost_5k"` |
| `status` | string | Business status: `"active"` / `"passed"` / `"failed"` / `"suspended_breach"` / `"suspended_fail"` / `"inactive"`. Treat unknown values conservatively |
| `agent_llm_score` | string | Latest agent reasoning score (e.g. `"72.5"`); `""` if non-agent or unscored |
| `agent_llm_score_at_ms` | int64 | Score time, Unix ms; `0` if absent |
| `assessment_start_at_ms` | int64 | Challenge assessment start (usually first effective fill), Unix ms; `0` if absent |
| `last_effective_trade_at_ms` | int64 | Latest effective fill time, Unix ms; `0` if absent |
| `profit_target_pct` | string | Program profit-target rate (percent string, e.g. `"10"`). Live since 2026-06-06 (aixfund Verify upgrade); upstream source field is `target_profit_pct`. |
| `min_trading_days` | int32 | Min required effective trading days; `0` means the program has no min-day rule. Upstream source field is `target_min_trading_days`. |
| `effective_trading_days_so_far` | int32 | Effective trading days achieved so far. Upstream source field is `valid_trading_days`. ⚠️ aixfund only ships a frozen snapshot when the account fails / is eliminated — for **active** accounts the value may stay at `0` even though server-side counting is happening. Do NOT interpret `0` on an active account as "zero days so far". |

`equity` sub-object (from risk-server + account-server):

| Field | Type | Notes |
| --- | --- | --- |
| `initial_capital` | string | Funded initial capital (USDT) |
| `baseline_equity` | string | Baseline equity (usually = `initial_capital`) |
| `current_equity` | string | Current equity (live balance + unrealized PnL, by mark_price) |
| `current_profit` | string | `current_equity - baseline_equity` (USDT, may be negative) |
| `current_profit_pct` | string | `(current - baseline) / baseline × 100`; `""` if `baseline_equity == 0` |

`risk` sub-object (from risk-server):

| Field | Type | Notes |
| --- | --- | --- |
| `max_drawdown_pct` | string | Max-cumulative-loss red line (percent); compare against `max_cumulative_loss_pct` |
| `current_drawdown_pct` | string | **Drawdown from the historical peak** (`(peak − current) / peak × 100`). ⚠️ NOT a cumulative-loss basis; not directly comparable to `max_drawdown_pct` |
| `max_daily_drawdown_pct` | string | Daily-drawdown red line (percent) |
| `last_daily_drawdown_pct` | string | Previous-day drawdown rate (daily_drawdown worker, 08:00 UTC daily). Always ≤ 0. `"0"` = flat / in profit / first day |
| `max_cumulative_loss_pct` | string | Max cumulative loss rate (`(baseline − min(trough, current)) / baseline × 100`). **Use this for the "max loss control" card**; same basis as `max_drawdown_pct`, directly comparable |
| `min_holding_seconds` | int | Minimum holding time (seconds). Currently fixed at `60`; later read from risk-control-server config |
| `short_hold_count_7d` | int | Rolling 7×24h count of `min_holding_time` rule events. First event = alert; second event = BREACH → account REVOKED. Live since 2026-06-06. |

Degraded behaviour when an upstream is unavailable:

| Upstream failure | Response handling | HTTP |
| --- | --- | --- |
| aixfund Verify did not send `account_challenges`, or no item matches `:id` | `aixfund: null`, other sub-objects returned normally | 200 |
| risk-server unavailable | `equity: null`, `risk: null` (only `aixfund` may have data) | 200 |
| account-server unavailable but risk-server OK | `equity.initial_capital: ""`, remaining `equity` fields computed from risk-server | 200 |
| **risk-server and account-server both unavailable** | whole request fails | 503 / 10501 |

The agent can degrade based on missing fields (`null` / `""` / `0`) without distinguishing by HTTP code. Note `min_holding_seconds` is a rule constant, not the current position's actual holding time.

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
curl "$BASE/markets/kline?exchange=$EXCH&symbol=BTC-USDT&interval=1m&limit=100"
```

> ⚠️ The query parameter is **`interval`**, NOT `timeframe`. The server
> silently ignores unknown params and falls back to `1m`, so passing
> `timeframe=5m` returns a stream of 1-minute candles with no error. The
> public WebSocket `ohlcv` topic uses `timeframe` — don't conflate the two.
> Valid values: `1m / 3m / 5m / 15m / 30m / 1h / 2h / 4h / 6h / 8h / 12h / 1d / 3d / 1w / 1M`.

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
