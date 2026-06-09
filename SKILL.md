---
name: aixfund-trading
description: Use when the user wants to trade on the AiXFund prop trading platform. Covers config setup, order placement / cancellation, leverage adjustment, position / balance / order / trade queries, market data, and risk-status checks. Trigger on mentions of AiXFund, prop trading, challenge mode, Lite or standard challenge, payout account, propdesk, or any concrete trading action like "place order", "cancel order", "check positions", "check balance", "set leverage", "query trades".
---

# AiXFund Trading Skill

Fully autonomous prop-trading agent skill. Wraps the propdesk HTTP API, providing config management, trading actions, and a risk snapshot.

**Version:** see the `VERSION` file at the skill root. Format is
`YYYY-MM-DD.N` where `N` is the release sequence within that day, starting
at `.1` (e.g. `2026-06-08.1`, `2026-06-08.2` for a second release the same
day). Read it to know which build is installed
(`cat skills/aixfund-trading/VERSION`). Bump it on every release: same day →
increment `N`; new day → reset to `.1`.

## Storage layout

Credentials and runtime state are kept in separate files:

- `~/.aixfund/accounts/<account_id>.json` — **credentials only** (token +
  exchange_account_id + three base URLs). Written by the STEP 2 terminal
  snippet the user pastes from https://aixfunded.com/app/agent-api. Scripts
  are read-only with these files.
- `<skill-root>/state.json` — per-skill runtime state: which account is
  currently bound (`active_account_id`), `mode`, `initial_balance`, and the
  cached `active_exchange`.

One skill install = one bound account. To operate two accounts in parallel,
install the skill twice (each copy has its own `state.json`).

## Active exchange is runtime-resolved (post 2026-05-15)

The backend picks the active exchange at runtime (currently `binance` on
testnet; previously `apex`). **You normally don't need to deal with it:**
`markets.py` subcommands default `--exchange` to the active value, and
`config.py bind` / `risk_status.py` cache it in `state.json`. Just don't
hardcode an exchange name. To read it explicitly, use `markets.py metadata`
(`data.active_exchange`).

Details, only if relevant:

- Responses always carry the active name in `data.exchange`. If it differs
  from your cached value, the backend has swapped — re-read metadata.
- The server accepts a stale `exchange=apex` and maps it to the active hub,
  so old clients keep working.
- **Reconciliation caveat:** query endpoints rewrite the `exchange` field on
  historical orders / trades / positions to the *current* active name, not
  the venue they executed on. For after-the-fact reconciliation use
  `created_at` + the swap timeline, not the `exchange` field.

**Available symbols are exchange-dependent.** Examples below use
`BTC-USDT` because the current active hub is binance, which quotes against
USDT. Earlier APEX listings used USDC. Do NOT hardcode the quote currency —
read `data.symbols[]` from `markets.py metadata` to discover what is
tradeable right now, and pick from that list.

## Workflow on first invocation in a session

### Step 1: check current binding

```bash
python3 skills/aixfund-trading/scripts/config.py show
```

Possible states:

- **`state.json` missing or no `active_account_id`**: not bound yet. If the
  user also hasn't pasted the STEP 2 terminal snippet, `~/.aixfund/accounts/`
  will be empty — direct them to https://aixfunded.com/app/agent-api to copy
  the snippet. Do NOT ask the user for their token; tokens must never pass
  through the agent context.
- **Bound to an account**: skip to Step 3.

### Step 2: bind the skill to an account

Trigger phrases like "Initialize challenge, account_id: xxxxx" or
"Rebind, account_id: yyyyy" both map to:

```bash
python3 skills/aixfund-trading/scripts/config.py bind --account-id <id>
```

`bind` is used for BOTH first-time init and later account switching. Same
command, just a different id.

What `bind` does:

1. Verifies `~/.aixfund/accounts/<id>.json` exists (paste the STEP 2 snippet
   if not).
2. Reads `mode` + `initial_balance` from `GET /exchange-accounts/:id/challenge`:
   `program_id` (e.g. `standard_5k` / `boost_10k`) gives the exact track and
   tier, and `baseline_equity` gives the funded amount. baseline_equity does
   not drift as the account trades, so a profitable / drawn-down account still
   resolves to the right tier. Falls back to `/exchange-accounts` if that
   endpoint is unavailable (which also covers PAYOUT phase).
3. Best-effort call to `/market/metadata` to cache `active_exchange`
   (skipped silently if the call fails — not a hard dependency).
4. Writes `state.json` with `active_account_id` + `mode` + `initial_balance`
   + `active_exchange`.

Extra subcommands:

- `config.py list-accounts` — list every credential file under
  `~/.aixfund/accounts/` and the currently bound id.
- `config.py migrate` — move a legacy `~/.aixfund/config.json` into the new
  layout automatically.

Legacy paths (only when the terminal snippet is not viable):

- `config.py bootstrap --token ...` — agent-driven init, token passes
  through the agent. Writes both credentials and state.

### Step 3: risk snapshot

```bash
python3 skills/aixfund-trading/scripts/risk_status.py
```

The agent presents a summary back to the user (account, current PnL, risk status, rule reminders).

### Step 4: enter autonomous trading

After the summary, the agent acts on the user's strategy instructions without confirming each individual order. Before any risk-sensitive action, the agent runs `risk_status.py` again and notes how close each threshold is.

## Command cheatsheet

See `scripts/README.md` for the full list. Common ones:

```bash
# Place order (market / limit)
python3 skills/aixfund-trading/scripts/place_order.py --symbol BTC-USDT --side BUY --order-type MARKET --size 0.001
python3 skills/aixfund-trading/scripts/place_order.py --symbol BTC-USDT --side BUY --order-type LIMIT --size 0.1 --price 60000

# Open with attached TP/SL in one shot (preferred — one API call, atomic)
python3 skills/aixfund-trading/scripts/place_order.py \
  --symbol BTC-USDT --side BUY --order-type MARKET --size 0.001 \
  --tp-price 80000 --sl-price 75000

# Standalone conditional order (separate TP or SL after entry)
python3 skills/aixfund-trading/scripts/place_order.py \
  --symbol BTC-USDT --side SELL --order-type TAKE_PROFIT_MARKET --size 0.001 \
  --trigger-price 80000 --trigger-type MARK --reduce-only

# Close a position (market reduce-only).
# --reasoning is required, same as place_order.py (the close is itself an
# agent-graded order). The 1-minute minimum hold rule is enforced server-side;
# this script does NOT gate on hold time, so pace your own closes.
python3 skills/aixfund-trading/scripts/close_position.py --symbol BTC-USDT --reasoning "..."
python3 skills/aixfund-trading/scripts/close_position.py --all --reasoning "..."

# Cancel
python3 skills/aixfund-trading/scripts/cancel_order.py --order-id 1234 --symbol BTC-USDT
python3 skills/aixfund-trading/scripts/cancel_order.py --all --symbol BTC-USDT   # non-conditional only

# Queries
python3 skills/aixfund-trading/scripts/query.py positions
python3 skills/aixfund-trading/scripts/query.py balance
python3 skills/aixfund-trading/scripts/query.py open-orders         # regular LIMIT/MARKET only
python3 skills/aixfund-trading/scripts/query.py condition-orders    # TP/SL/STOP trigger orders
python3 skills/aixfund-trading/scripts/query.py challenge           # merged assessment view (status + equity + risk + effective trading days)

# Market data
python3 skills/aixfund-trading/scripts/markets.py board
python3 skills/aixfund-trading/scripts/markets.py metadata        # also shows active_exchange
python3 skills/aixfund-trading/scripts/markets.py kline --symbol BTC-USDT --timeframe 1m --limit 100
# --exchange is optional; defaults to the active_exchange returned by /market/metadata
# (currently "binance" on testnet; previously "apex"). Override with --exchange <name> only if needed.

# Risk
python3 skills/aixfund-trading/scripts/risk_status.py

# Leverage
python3 skills/aixfund-trading/scripts/set_leverage.py --symbol BTC-USDT --leverage 5
```

## TP/SL mental model

The propdesk API splits orders into two queues:

- **Regular orders** (LIMIT, MARKET) → `query.py open-orders`.
- **Conditional orders** (STOP_*, TAKE_PROFIT_*) → `query.py condition-orders`.
  They sit in `UNTRIGGERED` / `PENDING` state until the trigger price is hit.

Two ways to set a stop-loss or take-profit:

1. **Attach on entry** (`place_order.py --tp-price X --sl-price Y`) — one atomic
   API call. The platform creates the entry order plus the TP and/or SL legs
   together as an OCO pair (one triggers → the other auto-cancels).
2. **Standalone trigger order** — a separate `STOP_MARKET` /
   `TAKE_PROFIT_MARKET` order with `--reduce-only`. Lives in the condition-order
   queue; cancel individually with `cancel_order.py --order-id <id>`.

Prefer #1 when opening. Use #2 to add / adjust after entry.

### Where to find attached TP/SL after submitting

The same TP/SL pair shows up in different queries depending on the entry's
lifecycle:

- **Entry still resting** (LIMIT not yet filled): the entry sits in
  `query.py open-orders`. Each entry row carries two extra arrays —
  `take_profit[]` and `stop_loss[]` (always present, possibly empty) —
  embedding the PENDING TP/SL legs with their own `order_id`s. Use those
  ids directly with `cancel_order.py --order-id`.
- **Entry filled** (position open): the entry leaves `open-orders`. The
  TP/SL legs continue under `query.py condition-orders` in `UNTRIGGERED` /
  `PENDING` state until they fire or get auto-cancelled by OCO/close.
- **Triggered or cancelled legs**: only visible in `condition-orders` /
  `history-orders`, never in the embedded arrays.

### Cancelling LIMIT entries with attached TP/SL

The backend cascade-cancels the attached TP/SL legs automatically when you
cancel an unfilled LIMIT entry — no extra cleanup needed. Same thing happens
when the entry fills and the position is later closed: the legs go to
`CANCELED` on their own. Don't issue extra cancels for the leg `order_id`s
returned in `take_profit[]` / `stop_loss[]`.

### Attached-TP/SL field rules

`is_open_tpsl_order=true` triggers the attach flow. Server requires:

- at least one of `is_set_open_tp` / `is_set_open_sl` to be `true`,
- whichever leg is enabled to have `*_trigger_price > 0`,
- `*_trigger_price_type` ∈ {`MARKET`, `MARK`, `INDEX`} (`ORACLE` not supported).

`place_order.py` builds these flags from `--tp-price` / `--sl-price` /
`--tpsl-trigger-type`; passing both `--tp-price` and `--sl-price` is the
common case.

## Slippage tip (MARKET orders)

Spread on this venue varies a lot by symbol. A MARKET order pays the
spread on entry and again on exit, and leverage multiplies how that
shows up in unrealized PnL.

Before a MARKET order, especially on a less-liquid symbol, glance at
`markets.py orderbook` and `markets.py contract` and mention the gap
between the relevant top-of-book price and mark to the user.

## Critical rules (agent must internalize)

See `references/risk-rules.md` and `references/challenge-rules.md`. Summary:

- **Hold time >= 1 minute** — sub-minute closes are a soft violation; the trade is rolled back, the account survives.
- **Max-loss and daily-drawdown are HARD violations** — one breach fails the challenge or recalls the Payout account. No warning, no waiver.
- **Max 5 orders per second per account** (rate limit).
- **Leverage caps**: Challenge 10X / **Payout 5X**. Payout is capped at 5X —
  ordering above 5X is rejected with an error.
- **Forbidden**: multi-account trading, hedging across accounts, quote-latency / mispricing exploits, high-frequency cancel/replace, third-party-managed accounts, manual/Agent boundary bypass.
- **Lite mode thresholds**: profit target 12%, max loss 3%, no daily drawdown, no time limit, no min trading days. Tier: $1k only. Reward on pass: $50.
- **Standard / Boost thresholds (challenge stage, same numbers)**: profit target 10%, max loss 6%, daily drawdown 3%, >= 7 valid trading days, no time limit.
  - Tiers: $5k / $10k / $15k / $25k / $50k. Agent mode supported on $5k / $10k / $15k; $25k / $50k are manual-only.
  - **Boost Bonus**: paid only on the Boost track, on the first successful Payout — bonus = first Payout amount × 20%, capped at $1,000, released as 5 equal tranches across the next 5 Payouts.
- **Payout stage**: 80% to trader; min withdrawal 100 USDT (first payout included); challenge fee is **not** refunded; payout request windows 5/15/25 (first request exempt); balance withdrawal windows 8/18/28; awards can be clawed back on later-discovered violations.
- **Inactivity suspension (30 days)**: an account is suspended after 30 calendar days without an executed fill. Logins, market-data reads, agent connections, placing/cancelling orders that never fill, and auto-liquidations do NOT count as activity. Only a real trade resets the clock.
- **Exploit duty**: if you notice a backend bug (mispriced fills, missing fees, stale data), report it instead of trading on it. Profits from exploiting it are clawback-eligible.
- **AI reasoning score (REQUIRED for agent-mode accounts)**: every order
  must carry a fresh, order-specific `--reasoning` string. The server
  **requires** this field on agent-mode accounts — missing or empty triggers
  `INVALID_ARGUMENT`. Length limit is **4096 bytes UTF-8**; over-limit is
  also rejected by the server. `place_order.py` validates both client-side
  and dies early if missing or too long. The platform LLM-grades sampled
  reasoning; baseline 60, LLM adds ±40, must stay >= 60 or the challenge
  fails. Templated/duplicate text is penalised −5 to −20 per instance.
  See `references/risk-rules.md` for examples.

Example good call:
```bash
python3 skills/aixfund-trading/scripts/place_order.py \
  --symbol BTC-USDT --side BUY --order-type MARKET --size 0.001 \
  --tp-price 80000 --sl-price 75000 \
  --reasoning "BTC 4H broke prior high at 68,500 on expanding volume and a MACD golden cross; sizing at 1% of equity, exit below breakout level to contain false-breakout risk."
```

## Failure fallback

If any `scripts/xxx.py` invocation fails, fall back in this order:

1. Use the generic caller: `python3 skills/aixfund-trading/scripts/api.py <METHOD> <PATH> [--query ...] [--json '...']`.
2. If that also fails, use curl from `references/api-http.md`.

The token and `exchange_account_id` always come from `~/.aixfund/config.json`.

## Reference docs

- `references/api-http.md` - HTTP API reference + curl examples.
- `references/api-websocket.md` - WebSocket protocol (no script wrapper in MVP).
- `references/data-types.md` - field definitions, order statuses, error codes.
- `references/challenge-rules.md` - challenge rules (aixfunded.com/challenge/rules).
- `references/risk-rules.md` - violation list + agent guidance.
- `scripts/README.md` - full script command reference.
