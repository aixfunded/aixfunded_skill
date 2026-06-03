# Challenge rules (aixfunded.com/challenge/rules is the source of truth)

> Source: https://aixfunded.com/challenge/rules. Where this document and
> the PRD differ, follow this document. Last refreshed against the live
> rules page on 2026-06-02.

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
- AI reasoning score (Agent mode only): >= 60.

## Boost mode

Per aixfunded.com/challenge/rules, Boost shares the **same challenge-stage
threshold table as Standard** (profit 10%, max-loss 6%, daily-drawdown 3%,
valid days >= 7, no time limit). Its differentiator is the Boost Bonus
paid on top of the first successful Payout (see "Boost Bonus" below);
Boost is more expensive at purchase to fund that bonus.

Tier sizes match Standard ($5k / $10k / $15k / $25k / $50k). Agent mode
is supported only on the smaller tiers; $25k and $50k are manual-only.

| Account size | Profit target | Max loss | Daily drawdown | Min trading days | Time limit | Profit split | Agent mode |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $5,000  | 10% | 6% | 3% | >= 7 days | unlimited | 80% / 20% (+ Bonus) | yes |
| $10,000 | 10% | 6% | 3% | >= 7 days | unlimited | 80% / 20% (+ Bonus) | yes |
| $15,000 | 10% | 6% | 3% | >= 7 days | unlimited | 80% / 20% (+ Bonus) | yes |
| $25,000 | 10% | 6% | 3% | >= 7 days | unlimited | 80% / 20% (+ Bonus) | no  |
| $50,000 | 10% | 6% | 3% | >= 7 days | unlimited | 80% / 20% (+ Bonus) | no  |

> Source-history note: an earlier internal Boost MRD listed stricter 12%
> profit / 5% max-loss targets and a 10-day deadline. The public rules
> page now lists Boost with the same numbers as Standard — that's the
> authoritative version.

### Boost Bonus (post-Payout reward)

Boost passes the same Payout phase as Standard, **plus** a one-time Boost Bonus tied to the first successful Payout:

- Triggered the first time the trader successfully Payouts on the Boost Payout account.
- **Bonus total = (first Payout amount paid to the trader) × 20%, capped at $1,000.**
  Note "first Payout amount paid to the trader" means the trader's split, not the gross profit. With the current 80% Payout split, a first profit of $3,000 yields a trader Payout of $2,400 and a bonus of $480.
- Released in **five equal tranches**, one per successful Payout. Each tranche posts as a separate ledger entry alongside that Payout's profit share.
- Per-tranche amount = bonus total ÷ 5.
- One Boost account = one Boost Bonus. After the 5th tranche posts, the bonus is exhausted.
- Suspended accounts (see the inactivity rule below) cannot release any remaining tranches.

Worked examples (using the current 80% split):
- Gross profit $3,000 → trader Payout $2,400 → bonus $480 → released as $96 × 5.
- Gross profit $10,000 → trader Payout $8,000 → bonus capped at $1,000 → released as $200 × 5.

> Note for the skill: `/exchange-accounts` does not yet expose a field that
> tells Standard and Boost apart at the $10k / $50k capital sizes (where
> both tracks have a tier). `config.py bind` defaults to Standard at those
> sizes. At capital points unique to one track ($5k / $15k / $25k →
> Standard only; $20k / $30k → Boost only) `bind` picks the only valid
> mode. To force a different mode, override with `python3 config.py bind
> --account-id <id> --skip-lookup --mode boost-NNk --initial-balance <amount>`.

## Leverage caps

- Challenge stage (Lite / Standard / Boost): **max 10X**
- Payout stage: **max 5X** (per aixfunded.com/challenge/rules)

## Payout stage

After passing Standard or Boost, the trader may receive a Payout simulated
account (subject to platform review and approval — passing the challenge
does not guarantee Payout access).

Risk thresholds (real-time, **hard violations** — one breach closes the
account; no warning, no second strike):

- Cumulative max loss < 6%.
- Daily max drawdown < 3%.

Soft conditions (do not fail the account, but block this payout request):

- Valid trading days: >= 7 cumulative valid days. Not satisfying this
  blocks the payout request but the account survives.
- Best trading day profit ratio < 50% — best day's profit divided by
  total profit-day profit in the current cycle. Each successful payout
  resets the cycle.
- Minimum profit per payout request: 100 USDT. Below this the request
  is rejected; keep trading until the threshold is met.

Profit split and timing:

- **80%** to the trader.
- **Payout request windows**: 5th / 15th / 25th of each month. The very
  first payout request is exempt from this window — the trader can
  submit as soon as the threshold conditions are met.
- **Balance withdrawal processing windows**: 8th / 18th / 28th of each
  month. Approved payout amounts land in the AiXFunded account balance;
  the trader then submits a withdrawal request, processed on these dates.
- **Minimum withdrawal: 100 USDT, including the first one.**
- **Challenge fee is NOT refunded** at any payout (the older "first
  payout refunds the entry fee" mechanic was removed).
- **Awards can be clawed back.** If the platform later finds rule
  violations, fraud, abuse, duplicate accounts, or risk-system errors,
  it can cancel, claw back, or adjust payouts and Boost Bonuses.

## Account-quota mechanism (front-end / informational)

The platform caps the combined simulated capital across every account
belonging to the same **Risk Entity** at **$200,000**. A Risk Entity is
the platform's grouping of accounts believed to be controlled by the
same real person or team, judged from device / network / KYC / wallet /
payment-source / behavioral signals — NOT just same user-id.

Quota is occupied by: active challenges, accounts pending Payout,
issued Payout accounts, accounts under risk review, and frozen accounts.
Quota is released by: failed challenges, voluntary closures, inactivity
suspensions, and revoked-for-violation closures.

This is enforced at challenge purchase on the website; the trading API
is not affected. The skill does not need to do anything with this rule,
but it is the answer to "why can't I buy a $50k challenge right now?"

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
