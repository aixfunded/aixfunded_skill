# Risk and violation rules

> Source: aixfunded.com/challenge/rules. Applies to every account
> regardless of mode / stage / size.

## Violation severity (per the live rules page)

The platform sorts violations into two tiers:

- **Soft violation** — the offending trade is rolled back (e.g. a sub-minute
  close is cancelled and the position is restored), but the account stays
  alive and can keep trading.
- **Hard violation** — max-loss or daily-drawdown breach. Challenge fails
  immediately; Payout account is recalled immediately. No warning, no
  human waiver, no second strike.

> **`min_holding_time` enforcement upgrade (2026-06-06).** Sub-minute closes
> are no longer purely soft: server-side risk now keeps a rolling 7×24h
> counter (`risk.short_hold_count_7d`). The **first** event in the window
> emits `MIN_HOLDING_ALERT` (the close is still rolled back, account
> survives). The **second** event in the same window emits
> `MIN_HOLDING_BREACH` → `REVOKE_ACCOUNT`: open orders cancelled, positions
> force-closed, account disabled. Treat any non-zero `short_hold_count_7d`
> as a serious warning, not a "soft tier survives" green light.

On either tier the platform can additionally claw back rewards, payouts,
or Boost Bonuses already credited, and may blacklist the email / KYC
identity / Risk Entity for repeat or severe abuse.

## Forbidden behavior

| # | Behavior | Notes |
| --- | --- | --- |
| 1 | Multi-account trading | Holding positions on two or more accounts at the same time. |
| 2 | Cross-account hedging / mirroring / copy-trading | Opposite or near-identical positions across accounts. |
| 3 | Exploiting quote latency / stale prices / mispricing | Strategies that depend on speed, latency, data-feed glitches, or known bugs. |
| 4 | High-frequency cancel/replace | Spamming orders/cancels. |
| 5 | Holding too briefly | Position held < 1 minute. First offence in any rolling 7d window = alert (close rolled back); second offence in the same window = BREACH → account revoked. |
| 6 | Unauthorized automation / third-party account management | Bots, scripts, copy-trade tools, signal services, or letting someone else trade your account. |
| 7 | Manual / Agent boundary bypass | A manual account must not be driven via API, and an Agent account must not be driven via the web UI. The choice is locked in at purchase. |
| 8 | Exploiting backend bugs | Any unintended platform behavior (mispricing, stale data, calculation bug) must be reported, not exploited. |
| 9 | Identity / quota evasion | Duplicate accounts, synthetic identity, VPN/VPS to fake jurisdiction, sharing API keys across accounts. |

> **Explicitly allowed:** news trading and holding positions over the weekend
> are both permitted. They still have to obey every risk and forbidden-behavior
> rule above — "allowed" is not a risk-rule exemption.

## Critical thresholds (agent must internalize)

| Threshold | Value | Source |
| --- | --- | --- |
| Min holding time per position | >= 1 minute (1st sub-minute close in any rolling 7d → alert; 2nd → REVOKE_ACCOUNT) | aixfunded.com/challenge/rules |
| Max orders per second per account | 5 | propdesk API doc (rate limit) |
| Max leverage in Challenge stage | 10X | aixfunded.com/challenge/rules |
| Max leverage in Payout stage | 5X | aixfunded.com/challenge/rules |

> ⚠️ **Payout is capped at 5X.** Ordering above 5X on a Payout account is
> rejected with an error. (The `/exchange-accounts` `max_leverage` field may
> show `20` — ignore it; the cap is 5X.) The cap is also
> **per-asset**: challenge sits in 5X–10X, Payout in 2X–5X, so for some
> assets the real ceiling is below these maxima — trust the order-time value.
| Inactivity suspension | 30 calendar days without a real fill | aixfunded.com/challenge/rules |

## Inactivity rule (suspension after 30 days)

The platform suspends any account that goes **30 consecutive calendar days
without an "effective trading action."** "Effective" means an order that
actually fills (results in an executed trade). The following do NOT count
and will NOT reset the clock:

- Logging in or viewing the dashboard
- Pulling market data (`markets.py board`, `kline`, `metadata`, etc.)
- Connecting the Agent or running `risk_status.py`
- Placing an order that never fills (LIMIT that sits open, then is cancelled)
- Cancelling orders
- Deposits, withdrawals
- System-initiated auto-liquidations

Implications for the agent:

- "Watching the market and waiting for a setup" can quietly burn the 30-day
  budget. Track the last actual fill (see `query.py trades` for the most
  recent `created_at`); if it has been over 20 days, consider whether to
  take a small, plan-consistent trade rather than risk suspension.
- A suspended account cannot trade, request Payout, or release Boost
  Bonus. The platform may notify the user when the remaining window drops
  below 10 days.

## AI reasoning score (agent-mode accounts)

`reasoning` is a **required** field on every order placed against an
agent-mode account. The server rejects a missing or over-limit `reasoning`
with `INVALID_ARGUMENT` (it is not merely a score penalty). In addition,
the platform grades agent performance via an "AI reasoning score" that is
independent of PnL — failing this score fails the challenge even if PnL
targets are met.

| Item | Value | Notes |
| --- | --- | --- |
| Starting score | 60 | Assigned when the challenge begins. |
| LLM grading range | ±40 | Sampled `reasoning` strings are scored by LLM. |
| Pass threshold | >= 60 | Below this the agent is flagged invalid. |
| Duplicate penalty | −5 to −20 per instance | Templated / repeated text is punished. |

Implications for the agent:

- **Always pass `--reasoning`** to `place_order.py` on agent-mode accounts.
  The server rejects orders without it (`INVALID_ARGUMENT`).
- **Write order-specific rationale.** Reference the actual setup: indicators
  checked, price levels, sizing logic, and contingency (stop / exit plan).
- **Never reuse text across orders.** Even minor edits beat copy-paste.
- **Stay within 4096 bytes (UTF-8).** Chinese characters count ~3 bytes each.
  Over-limit returns `INVALID_ARGUMENT`; the client also validates and dies
  early with a byte count.
- **Prefer substance over length.** "Continue buy" / "ok" / empty strings are
  high-risk triggers for the duplicate penalty.

High-quality example (from platform docs):
> "BTC 4H breaks prior high at $68,500; volume expanding and MACD golden cross
> suggest trend continuation. Sizing at 5% of equity; exit below the breakout
> level to contain false-breakout risk."

## Practical guidance for the agent

1. **Hold control:** wait at least 65 seconds after opening before considering a close (5-second buffer to avoid edge violations). Check `risk.short_hold_count_7d` via `risk_status.py` / `query.py challenge`; if it is already `1` (one alert in the past 7 days), the next sub-minute close revokes the account — be extra deliberate.
2. **Order pacing:** when batching, sleep >= 250 ms between orders to stay under the 5/s limit.
3. **Same-direction only:** never open opposing positions on the same symbol within a single account (avoid hedge classification).
4. **Live quotes:** rely on `/markets/orderbook` snapshots, not stale ticker data.
5. **Risk-first:** before opening new exposure, run `risk_status.py`.
   Stop opening new positions when max-loss usage is within 1 percentage
   point of the limit (>= 5% drawn on a 6% cap — Standard/Boost Payout and
   Standard challenge; >= 4% on a 5% cap — **Boost challenge stage**;
   >= 2% on a 3% Lite cap). Max-loss and daily-drawdown are hard violations
   — one breach ends the account.
6. **Reason every trade:** on every `place_order.py` / `close_position.py`
   call, pass a fresh order-specific `--reasoning` string (see AI
   reasoning score section above).
7. **Report, don't exploit:** if you notice a backend bug or unintended
   behavior (mispriced fills, missing fees, stale data, off-by-one in
   a margin calc), stop trading and report it. Profits from exploiting
   it are clawback-eligible per the rules.
