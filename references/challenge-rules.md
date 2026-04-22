# Challenge rules (aixfunded.com/plans is the source of truth)

> Where this document and the PRD differ, follow this document. Source: https://aixfunded.com/plans.
> Payout-stage details are not on the public plans page, so they fall back to the PRD (marked "PRD source").

## Lite mode

| Field | Value |
| --- | --- |
| Account size | $1,000 (simulated) |
| Entry fee | $9.9 (non-refundable) |
| Profit target | 8% (>= $80) |
| Max loss | 5% (<= $50) |
| Daily drawdown | none |
| Min trading days | none |
| Time limit | unlimited |
| Reward on pass | $50 cash |
| Payout stage | none |
| Trading methods | manual + Agent |

## Standard mode

| Account size | Fee | Profit target | Max loss | Daily drawdown | Min trading days | Time limit | Profit split |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $10,000 | $69 | 10% | 6% | 3% | >= 7 days | 10 days | 70% / 30% |
| $20,000 | $129 | 10% | 6% | 3% | >= 7 days | 10 days | 70% / 30% |
| $30,000 | $189 | 10% | 6% | 3% | >= 7 days | 10 days | 70% / 30% |
| $50,000 | $289 | 10% | 6% | 3% | >= 7 days | 10 days | 70% / 30% |

Evaluation details:
- Profit target: account reaches 10% return. Evaluated daily at 08:00 UTC. Must have no open positions and (available - initial) > 10%.
- Max loss: account equity must never drop below 94% of the initial (includes unrealized PnL); evaluated every 5 min or in real time.
- Daily drawdown: equity drop must not exceed 3% of the previous day's equity (includes unrealized PnL). Resets daily at 08:00 UTC.
- Valid trading days: a day counts if (cumulative trade volume / previous day total equity) > 60%.
- Time limit: failure if not completed within 10 days.
- AI reasoning score (Agent mode only): > 60.

## Leverage caps

- Challenge stage (Lite / standard): **max 10X**
- Payout stage: **max 20X**

## Payout stage (PRD source)

After passing standard mode, the trader receives a Payout simulated account.

Risk thresholds (real-time):
- Cumulative max loss < 6% (account is recalled at 6%).
- Daily max drawdown < 3% (1 trigger per week is a warning; 2 triggers recall the account and revoke Payout eligibility).
- Valid trading days: at least 60% of the period (not a violation, but affects withdrawals).
- Best trading day profit ratio < 50% (not a violation, but affects withdrawals).

Profit split:
- 70% (standard mode).
- Distribution dates: 5th / 15th / 25th of each month.
- The original challenge fee is refunded after the first payout (issued as 2 separate ledger entries).

## Agent mode extras

- AI reasoning score >= 60 (every order must include a `reasoning` field; otherwise the challenge fails).
- Once Agent mode is selected, the account cannot use the manual front end (mutually exclusive).
