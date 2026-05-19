# Challenge rules (aixfunded.com/plans is the source of truth)

> Where this document and the PRD differ, follow this document. Source: https://aixfunded.com/plans.
> Payout-stage details that are not on the public plans page fall back to the PRD (marked "PRD source").
> Last refreshed against the 2026-05-14 parameter update.

## Lite mode

| Field | Value |
| --- | --- |
| Account size | $1,000 (simulated) |
| Profit target | **12%** (>= $120) |
| Max loss | **3%** (<= $30) |
| Daily drawdown | none |
| Min trading days | none |
| Time limit | unlimited |
| Reward on pass | $50 cash |
| Payout stage | none |
| Trading methods | manual + Agent |

> 2026-05-14 change: profit target raised from 8% to 12%, max loss tightened from 5% to 3%.

## Standard mode

Available tiers ($5k / $10k / $15k / $25k / $50k). The previous $20k and $30k tiers are retired. Agent mode is supported only on the smaller tiers — the $25k and $50k accounts are manual-only.

| Account size | Profit target | Max loss | Daily drawdown | Min trading days | Time limit | Profit split | Agent mode |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $5,000  | 10% | 6% | 3% | >= 7 days | **unlimited** | **80% / 20%** | yes |
| $10,000 | 10% | 6% | 3% | >= 7 days | **unlimited** | **80% / 20%** | yes |
| $15,000 | 10% | 6% | 3% | >= 7 days | **unlimited** | **80% / 20%** | yes |
| $25,000 | 10% | 6% | 3% | >= 7 days | **unlimited** | **80% / 20%** | no  |
| $50,000 | 10% | 6% | 3% | >= 7 days | **unlimited** | **80% / 20%** | no  |

Evaluation details:
- Profit target: account reaches 10% return. Evaluated daily at 08:00 UTC. Must have no open positions and (available - initial) > 10%.
- Max loss: account equity must never drop below 94% of the initial (includes unrealized PnL); evaluated every 5 min or in real time.
- Daily drawdown: equity drop must not exceed 3% of the previous day's equity (includes unrealized PnL). Resets daily at 08:00 UTC.
- Valid trading days: a day counts if (cumulative trade volume / previous day total equity) > 60%.
- Time limit: **removed** — there is no longer a 10-day completion deadline. The challenge can run as long as the account stays active (see the inactivity rule below).
- AI reasoning score (Agent mode only): > 60.

## Boost mode

A new track introduced in the 2026-05-14 update. Threshold-wise it mirrors Standard but is priced separately (priced higher because Boost rewards faster compounding) and uses the lowered "valid trading days >= 7" target. Tier sizes are identical to Standard — $5k / $10k / $15k / $25k / $50k. As with Standard, only the smaller tiers support Agent mode; $25k and $50k are manual-only.

Threshold table is the same as Standard (10% / 6% / 3% / >= 7 days / unlimited time / 80% split).

> Note for the skill: `/exchange-accounts` does not currently expose a field
> distinguishing Boost from Standard at the same capital. Until it does,
> `config.py bind` infers Standard by default. If you know the account is
> Boost, override with `python3 config.py bind --account-id <id>
> --skip-lookup --mode boost-NNk --initial-balance <amount>`.

## Leverage caps

- Challenge stage (Lite / Standard / Boost): **max 10X**
- Payout stage: **max 20X**

## Payout stage (PRD source + 2026-05-14 update)

After passing Standard or Boost, the trader receives a Payout simulated account.

Risk thresholds (real-time):
- Cumulative max loss < 6% (account is recalled at 6%).
- Daily max drawdown < 3% (1 trigger per week is a warning; 2 triggers recall the account and revoke Payout eligibility).
- Valid trading days: at least 60% of the period (not a violation, but affects withdrawals).
- Best trading day profit ratio < 50% (not a violation, but affects withdrawals).

Profit split and withdrawals:
- **80%** to the trader (raised from 70% in the 2026-05-14 update).
- Distribution dates: 5th / 15th / 25th of each month.
- **Minimum withdrawal: $100, including the first one.** (Previously the first withdrawal was exempt; now every payout request must be >= $100.)
- **Challenge fee is NOT refunded.** The previous "first payout refunds the original entry fee" mechanic was removed in the 2026-05-14 update.

## Account-quota mechanism (front-end / informational)

The platform caps every user's combined simulated capital at **$200,000** across all live Payout, pending-Payout, and active-challenge accounts. Past this cap, buying additional challenges is blocked. This is enforced at challenge purchase on the website — the trading API is not affected. Released when an account fails, expires, or is refunded; held when an account is under risk review.

The skill does not need to do anything with this rule, but it is the answer to "why can't I buy a $50k challenge right now?"

## Inactivity rule (skill-relevant)

An account is **suspended after 30 calendar days without an "effective trading action."**
What counts:
- **Activity (resets the 30-day clock):** an order that **actually fills** (results in an executed trade).
- **NOT activity:** logging in, viewing market data, connecting the Agent, placing or cancelling orders that never fill, deposits, withdrawals, system auto-liquidation.

Implications for the agent:
- Long idle periods are dangerous even if the agent is "connected and watching." Place at least one filling trade per 30-day window.
- Cancelling-and-replacing without a fill does not extend the window.
- Suspended accounts cannot trade, cannot request Payout, and cannot release Boost bonuses; their quota is returned to the user's account-quota pool.

## Agent mode extras

- AI reasoning score >= 60 (every order must include a `reasoning` field; otherwise the challenge fails).
- Once Agent mode is selected, the account cannot use the manual front end (mutually exclusive).
- Agent mode is not available on the $25k or $50k tiers (Standard or Boost). The smaller tiers ($5k / $10k / $15k) support Agent.
