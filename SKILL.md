---
name: aixfund-trading
description: Use when the user wants to trade on the AiXFund prop trading platform. Covers config setup, order placement / cancellation, leverage adjustment, position / balance / order / trade queries, market data, and risk-status checks. Trigger on mentions of AiXFund, prop trading, challenge mode, Lite or standard challenge, payout account, propdesk, or any concrete trading action like "place order", "cancel order", "check positions", "check balance", "set leverage", "query trades".
---

# AiXFund Trading Skill

Fully autonomous prop-trading agent skill. Wraps the propdesk HTTP API, providing config management, trading actions, and a risk snapshot.

## Storage layout

Credentials and runtime state are kept in separate files:

- `~/.aixfund/accounts/<account_id>.json` — **credentials only** (token +
  exchange_account_id + three base URLs). Written by the STEP 2 terminal
  snippet the user pastes from https://aixfunded.com/app/agent-api. Scripts
  are read-only with these files.
- `<skill-root>/state.json` — per-skill runtime state: which account is
  currently bound (`active_account_id`), `mode`, `initial_balance`, and the
  stamped `challenge_start_ts` / `challenge_start_date_utc`.

One skill install = one bound account. To operate two accounts in parallel,
install the skill twice (each copy has its own `state.json`).

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
command, just a different id. If the user names a new id while an older one
is already bound, the challenge clock is cleared automatically.

What `bind` does:

1. Verifies `~/.aixfund/accounts/<id>.json` exists (paste the STEP 2 snippet
   if not).
2. Calls `GET /exchange-accounts` with the token in that file.
3. Infers `mode` from `initial_capital` (1000→lite, 10000→standard-10k,
   20000→standard-20k, 30000→standard-30k, 50000→standard-50k) or sets
   `mode=payout` when `account_phase=="PAYOUT"`.
4. Writes `state.json` with `active_account_id` + `mode` + `initial_balance`.

Never ask the user for a challenge start date. The challenge period starts
automatically at the first successful order placement —
`place_order.py` stamps `challenge_start_ts` (UTC seconds) into `state.json`
from the server's `Date` response header. Until that happens `risk_status.py`
reports `challenge_started: false`.

Extra subcommands:

- `config.py list-accounts` — list every credential file under
  `~/.aixfund/accounts/` and the currently bound id.
- `config.py reset-challenge` — clear the stamped `challenge_start_ts` (use
  when the platform resets the challenge).
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

# Close a position (market reduce-only, enforces 1-min min-hold)
python3 skills/aixfund-trading/scripts/close_position.py --symbol BTC-USDT
python3 skills/aixfund-trading/scripts/close_position.py --all

# Cancel
python3 skills/aixfund-trading/scripts/cancel_order.py --order-id 1234 --symbol BTC-USDT
python3 skills/aixfund-trading/scripts/cancel_order.py --all --symbol BTC-USDT   # non-conditional only

# Queries
python3 skills/aixfund-trading/scripts/query.py positions
python3 skills/aixfund-trading/scripts/query.py balance
python3 skills/aixfund-trading/scripts/query.py open-orders         # regular LIMIT/MARKET only
python3 skills/aixfund-trading/scripts/query.py condition-orders    # TP/SL/STOP trigger orders

# Market data
python3 skills/aixfund-trading/scripts/markets.py board
python3 skills/aixfund-trading/scripts/markets.py kline --exchange apex --symbol BTC-USDT --timeframe 1m --limit 100

# Risk
python3 skills/aixfund-trading/scripts/risk_status.py

# Leverage
python3 skills/aixfund-trading/scripts/set_leverage.py --symbol BTC-USDT --leverage 5
```

## TP/SL mental model

The propdesk API splits orders into two queues:

- **Regular orders** (LIMIT, MARKET) → `query.py open-orders`.
- **Conditional orders** (STOP_*, TAKE_PROFIT_*) → `query.py condition-orders`.
  They sit in `UNTRIGGERED` state until the mark/index price hits the trigger.

Two ways to set a stop-loss or take-profit:

1. **Attach on entry** (`place_order.py --tp-price X --sl-price Y`) — one atomic
   API call, the platform manages both legs as part of the position.
2. **Standalone trigger order** — a separate `STOP_MARKET` /
   `TAKE_PROFIT_MARKET` order with `--reduce-only`. Lives in the condition-order
   queue; cancel individually with `cancel_order.py --order-id <id>`.

Prefer #1 when opening. Use #2 to add / adjust after entry.

## Critical rules (agent must internalize)

See `references/risk-rules.md` and `references/challenge-rules.md`. Summary:

- **Hold time >= 1 minute** (anything less is a violation).
- **Max 5 orders per second per account** (rate limit).
- **Leverage caps**: Challenge 10X / Payout 20X.
- **Forbidden**: multi-account opening, multi-account hedging, quote-delay exploits, high-frequency cancel/replace.
- **Standard mode thresholds**: profit target 10%, max loss 6%, daily drawdown 3%, >= 7 valid trading days, 10-day evaluation period.
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
- `references/challenge-rules.md` - challenge rules (aixfunded.com/plans).
- `references/risk-rules.md` - violation list + agent guidance.
- `scripts/README.md` - full script command reference.
