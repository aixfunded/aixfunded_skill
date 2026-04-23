# Risk and violation rules (PRD source)

> Applies to every account regardless of mode / stage / size. On a confirmed violation:
> - Challenge accounts: challenge marked failed.
> - Payout accounts: account recalled.
> - Severe cases: email blacklisted.

## Forbidden behavior

| # | Behavior | Notes |
| --- | --- | --- |
| 1 | Opening positions on multiple accounts | Trading the same flow across multiple challenge / Payout accounts simultaneously. |
| 2 | Cross-account hedging | Opening opposite-direction positions on the same symbol across accounts. |
| 3 | Exploiting quote latency | Using stale-quote arbitrage tactics. |
| 4 | High-frequency cancel/replace | Spamming orders/cancels. |
| 5 | Holding too briefly | Position held < 1 minute. |
| 6 | Other cheating | Platform reserves judgment. |

## Critical thresholds (agent must internalize)

| Threshold | Value | Source |
| --- | --- | --- |
| Min holding time per position | >= 1 minute | PRD |
| Max orders per second per account | 5 | propdesk API doc (rate limit) |
| Max leverage in Challenge stage | 10X | aixfunded.com/plans |
| Max leverage in Payout stage | 20X | aixfunded.com/plans |

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

1. **Hold control:** wait at least 65 seconds after opening before considering a close (5-second buffer to avoid edge violations).
2. **Order pacing:** when batching, sleep >= 250 ms between orders to stay under the 5/s limit.
3. **Same-direction only:** never open opposing positions on the same symbol within a single account (avoid hedge classification).
4. **Live quotes:** rely on `/markets/orderbook` snapshots, not stale ticker data.
5. **Risk-first:** before opening new exposure, run `risk_status.py`. If max-loss usage is >= 5%, stop opening new positions.
6. **Reason every trade:** on every `place_order.py` call, pass a fresh
   order-specific `--reasoning` string (see AI reasoning score section above).
