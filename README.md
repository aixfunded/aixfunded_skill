# AiXFunded Trading Skill

An AI agent skill for interacting with the [AiXFunded](https://aixfunded.com) prop-trading platform. Works with Claude Code, OpenClaw, and other agents that support the Claude skill format.

With this skill installed, you can give natural-language instructions to your agent:

> "Buy 0.001 BTC with a stop at 75000"
> "Show my positions and risk status"
> "Close all SOL positions"

and the agent will call the right AiXFunded APIs on your behalf — without the token ever passing through the chat.

## Install in three steps

The AiXFunded dashboard (https://aixfunded.com/app/agent-api) generates the exact snippets for steps 1-3 prefilled with your account id. The outline:

1. **Install the skill.** Ask your AI agent to download `https://aixfunded.com/downloads/aixfunded-trading.skill` and unpack it into `~/.claude/skills/` (macOS/Linux) or `%USERPROFILE%\.claude\skills\` (Windows).

2. **Write credentials locally.** Paste a terminal snippet from the dashboard. It writes `~/.aixfund/accounts/<account_id>.json` containing your token and API URLs — this step runs only on your machine, the token never reaches the agent.

3. **Bind the skill.** Tell the agent: *"Initialize challenge, account_id: xxxxx"*. The agent runs `python3 scripts/config.py bind --account-id xxxxx`, which calls `/exchange-accounts` to infer `mode` / `initial_balance` and writes `state.json`.

The same `bind` command also handles account switching later (*"Switch binding, account_id: yyyyy"*).

## What's inside

| Component | Purpose |
|---|---|
| `SKILL.md` | Skill entry point read by the agent. Describes workflow and rules. |
| `scripts/` | Python 3.9+ CLIs wrapping the AiXFunded HTTP API (zero third-party deps). |
| `references/` | API reference, challenge rules, risk rules, data-type docs. |

### Scripts overview

| Script | Purpose |
|---|---|
| `config.py` | Manage skill binding: `show`, `list-accounts`, `bind`, `reset-challenge`, `migrate`, `bootstrap` |
| `place_order.py` | Place orders (market / limit / stop / take-profit). Supports attached TP/SL and `--reasoning` for agent-mode challenges. |
| `close_position.py` | Close positions via market reduce-only. Enforces the 1-minute min-hold rule. |
| `cancel_order.py` | Cancel single or all open orders. |
| `query.py` | Query `positions`, `balance`, `open-orders`, `condition-orders`, `history-orders`, `trades`, `pnl-closed`, `leverage`. |
| `markets.py` | Public market data: board, kline, orderbook, trades, contract summary. |
| `set_leverage.py` | Adjust leverage (respecting per-mode caps: Challenge 10x, Payout 20x). |
| `risk_status.py` | Unified risk snapshot: balance + open positions + per-mode thresholds + challenge period. |
| `auth_check.py` | Validate token and list authorized accounts. |
| `api.py` | Generic HTTP fallback for any endpoint not wrapped above. |

## Storage layout

Credentials and runtime state are kept apart so account state changes never disturb credentials:

```
~/.aixfund/accounts/<account_id>.json   # credentials (token + URLs), one per account
<skill-root>/state.json                 # which account is bound + mode + challenge clock
```

One skill install binds to one account. To operate multiple accounts in parallel, install the skill twice.

## Key rules for the agent

- **Minimum hold time:** 1 minute per position.
- **Rate limit:** max 5 orders per second per account.
- **Leverage caps:** Challenge 10x, Payout 20x.
- **Forbidden:** multi-account opening, multi-account hedging, quote-delay exploits, high-frequency cancel/replace.
- **AI reasoning score (agent-mode accounts):** every order MUST carry a fresh, order-specific `--reasoning` string (<= 4096 bytes UTF-8). The server rejects missing / over-limit values with `INVALID_ARGUMENT`. Sampled reasoning is LLM-graded; baseline 60, ±40 from grading, must stay >= 60. Templated / duplicate text incurs a -5 to -20 penalty per instance.
- **Challenge clock:** starts automatically on the first successful order (stamped from the server `Date` header, UTC).

Full details in [references/risk-rules.md](references/risk-rules.md) and [references/challenge-rules.md](references/challenge-rules.md).

## Privacy model

- **The token never reaches the AI.** The terminal snippet writes it directly to a local file; scripts read it from disk in a subprocess. The agent's chat context only sees the account id.
- **Server URLs are pinned in the credential file.** Switch environments by re-running STEP 2 with a new snippet — no code edit needed.
- **The skill can be sandboxed.** Use `.claude/settings.json` to deny direct reads of `~/.aixfund/accounts/**` if you want to prevent the agent from ever ingesting the token bytes.

## Platform

- Website: https://aixfunded.com
- Agent setup page: https://aixfunded.com/app/agent-api
- Skill download: https://aixfunded.com/downloads/aixfunded-trading.skill
