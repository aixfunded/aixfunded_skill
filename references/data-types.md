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
| exchange | Exchange identifier, e.g. "apex" |
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
| funding_fee | Funding fee accrual |
| account_type | PAPER / LIVE |
| imr | Initial margin requirement |

## Balance fields (returned by /portfolio/balances)

| Field | Notes |
| --- | --- |
| exchange_account_id | Account ID |
| total_equity_value | Total equity (incl. unrealized PnL) |
| available_balance | Available balance |
| initial_margin | Initial margin used |
| maintenance_margin | Maintenance margin |
| unrealized_pnl | Unrealized PnL |
| realized_pnl | Realized PnL |
| wallet_balance | Wallet balance |

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
