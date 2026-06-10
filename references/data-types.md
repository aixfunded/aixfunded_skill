# Data types and field reference

## General rules

- **Money fields** are strings (decimal), e.g. `"60000"`, `"0.1"`. Avoids float precision issues.
- **Timestamps** are int64 Unix microseconds, e.g. `1712534400000000`.
- **IDs** in HTTP responses are strings.

## Order fields (returned by openOrders / historyOrders)

| Field | Notes |
| --- | --- |
| order_id | Internal order ID |
| exchange_order_id | Exchange-side order ID |
| exchange | Exchange identifier; runtime-resolved on the server. Currently "binance" on testnet; previously "apex". On queries the server **rewrites this field to the active name regardless of where the order originally executed** — do NOT use it for cross-venue reconciliation; use `created_at` + the swap timeline instead. |
| exchange_account_id | Account ID |
| client_order_id | Client-supplied ID (auto-generated as `agent-{ms}-{uuid8}` by `place_order.py`) |
| symbol | Trading pair |
| side | BUY / SELL |
| order_type | LIMIT / MARKET / STOP_LIMIT / STOP_MARKET / TAKE_PROFIT_LIMIT / TAKE_PROFIT_MARKET |
| price | Submitted price |
| size | Submitted quantity |
| filled_size | Filled quantity |
| avg_price | Average fill price |
| status | See enum below |
| trigger_price | Trigger price (for conditional orders) |
| fee | Fee amount |
| account_type | PAPER (simulated) / LIVE |
| execution_type | Currently fixed at `"Trade"`; will return the real value once Maker/Taker distinction is supported. Also present on `/trades` entries. |
| err_code, err_msg | Failure details |
| created_at, updated_at | Unix microseconds |

### Order status enum

| Status | Notes |
| --- | --- |
| PENDING | Submitted, not yet filled |
| FILLED | Completely filled |
| PARTIALLY_FILLED | Partially filled |
| CANCELED | Canceled |
| REJECTED | Rejected by exchange |
| EXPIRED | Expired |

> Trust the API response when in doubt; the table above lists the common values.

## Position fields (returned by /positions)

| Field | Notes |
| --- | --- |
| exchange_account_id | Account ID |
| exchange | Exchange identifier |
| symbol | Trading pair |
| side | LONG / SHORT |
| quantity | Position size |
| entry_price | Average entry price |
| mark_price | Mark price |
| last_price | Last trade price |
| leverage | Current leverage |
| margin_mode | CROSS / ISOLATED |
| position_value | Notional value |
| liquidation_price | Liquidation price |
| unrealized_pnl | Unrealized PnL |
| unrealized_pnl_percent | Unrealized PnL % |
| funding_fee | This position's **cumulative settled** funding fee (sum since `created_at`). **Positive = paid by the user, negative = received by the user.** `"0"` when there are no records. |
| account_type | PAPER / LIVE |
| imr | Initial margin requirement |

## Balance fields (returned by /portfolio/balances)

| Field | Notes |
| --- | --- |
| exchange_account_id | Account ID |
| total_equity_value | Total equity (incl. unrealized PnL) — same basis as risk-server `current_equity`. |
| available_balance | `wallet_balance − initial_margin − frozen_for_orders`. |
| initial_margin | Initial margin used by open positions. |
| maintenance_margin | Maintenance margin (tier-based). |
| frozen_for_orders | Margin pre-frozen by OPEN LIMIT orders (reduce-only orders don't freeze). Released on cancel / reject / fill. |
| unrealized_pnl | Unrealized PnL (by `mark_price`). |
| realized_pnl | **Gross** realised PnL — does NOT subtract fees / funding. |
| realized_pnl_net | **Net** realised PnL = `realized_pnl − cumulative_fee + cumulative_funding`. Use this for "realised PnL" displays. |
| cumulative_fee | Lifetime fees paid (open + close). |
| cumulative_funding | Lifetime funding settled. **Positive = paid by user, negative = received** (same sign convention as `/positions.funding_fee`). |
| wallet_balance | `initial_capital + realized_pnl − cumulative_fee + cumulative_funding`. |

## Closed-PnL fields (returned by /pnl/closed)

| Field | Notes |
| --- | --- |
| side | **Opening direction**: `"BUY"` = LONG / `"SELL"` = SHORT (the entry order's side). |
| leverage | int. The leverage in effect when the position was closed (snapshot at close, after any auto step-down). A later `setLeverage` does not change it. Never returns 0. |
| funding_fee | Same sign convention as positions: **positive = paid by the user, negative = received by the user.** |

## Risk sub-object fields (returned by /exchange-accounts and /exchange-accounts/:id/challenge)

| Field | Notes |
| --- | --- |
| max_cumulative_loss_pct | Loss from baseline, percent = `(baseline − min(trough, current)) / baseline × 100`; `"0"` while in profit. **This is the max-loss figure — compare it against `max_drawdown_pct` to check the red line.** |
| last_daily_drawdown_pct | Previous day's drawdown, percent (daily_drawdown worker, once a day at 08:00 UTC). Always ≤ 0; `"0"` = flat / in profit / first day. **Compare against `max_daily_drawdown_pct`** (breach: `last < -max`). Daily snapshot, not an intraday value. |
| current_drawdown_pct | Pullback from the historical peak, percent = `(peak − current) / peak × 100`. Display-only — it grows when an account gives back profit, so it is not a loss figure. **Use `max_cumulative_loss_pct`, not this, for the red line.** |
| min_holding_seconds | int. Minimum holding time (seconds), a rule constant. Currently fixed at `60`; later read from risk-control-server config. Returned by `/exchange-accounts/:id/challenge`. |
| short_hold_count_7d | int. Rolling 7×24h count of `min_holding_time` rule events. `0` = clean; `1` = alert recorded (one strike); `2+` = BREACH → account REVOKED. Live since 2026-06-06. |

## trigger_type values

| Value | Notes |
| --- | --- |
| ORACLE | Oracle price |
| INDEX | Index price |
| MARKET | Market price |
| MARK | Mark price |

## time_in_force values

| Value | Notes |
| --- | --- |
| GTC | Good-Till-Cancel (LIMIT default) |
| FOK | Fill-Or-Kill |
| IOC | Immediate-Or-Cancel |
| POST_ONLY | Post-only |

## Error codes

See the error code table in `api-http.md` (10001 - 10008).
