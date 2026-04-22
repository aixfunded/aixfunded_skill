# WebSocket reference

> WebSocket is out of scope for the MVP scripts (no `api.py WS-*`). If the agent needs realtime feeds, hand-roll based on this doc.
> Full protocol: project root `aixfund-integration-http-ws.md` section 4.

## Private WS (orders / positions / balance)

**URL:** `ws://<AIXFUND_HOST>:8087/realtime_private[?user_mark=web]`
**Message size limit:** 32 KB

### Flow

```
1. Open WS connection
2. Send login message
3. Receive login success response
4. Send subscribe to topics
5. Receive snapshots + subsequent events
6. Bidirectional heartbeat
```

### login

```json
{"type":"login","args":["<aixfund-token>"]}
```

Success:
```json
{"type":"login","msg":"success","user_id":"...","request_id":"...","user_mark":"web"}
```

### subscribe

```json
{"type":"subscribe","args":["order","position","balance","trade"]}
```

Available topics:
| Topic | Aliases | Notes |
| --- | --- | --- |
| order | orders | Order status updates |
| position | positions | Position changes |
| balance | balances | Balance changes |
| trade | trades | Fill events |

A snapshot is auto-pushed after a successful subscribe.

### Manual snapshot request

```json
{"type":"snapshot","args":["position"]}
```

Limit: 1 request per 2 seconds per topic.

### unsubscribe

```json
{"type":"unsubscribe","args":["order"]}
```

### Heartbeat

```json
// Client -> server
{"type":"ping"}
// Server -> client
{"type":"pong"}
```

Recommended: client sends ping every 15-20s. Server pings every 30s.

### Event payload

```json
{"type":"event","topic":"order","user_id":"...","event_type":"order_filled","data":{...}}
```

---

## Public WS (market data)

**URL:** `ws://<AIXFUND_HOST>:8086/realtime_public`
**No auth.**

### subscribe

```json
{"action":"subscribe","exchange":"apex","topic":"ticker","symbol":"BTC-USDC"}
```

Available topics:
| Topic | Required parameters |
| --- | --- |
| ticker | exchange (symbol optional) |
| orderbook | exchange + symbol |
| trades | exchange + symbol |
| ohlcv | exchange + symbol + timeframe (e.g. 1m / 5m / 1h / 1d) + optional limit |

### unsubscribe

```json
{"action":"unsubscribe","exchange":"apex","topic":"ticker","symbol":"BTC-USDC"}
```

### Heartbeat

```json
{"action":"ping"}
{"type":"pong"}
```

### Push payload

```json
{"type":"data","topic":"ticker","symbol":"BTC-USDC","exchange":"apex","data":{...}}
```

---

## Tooling notes

This skill ships **no** WebSocket client -- Python stdlib does not include one and the skill avoids third-party dependencies. If the agent needs to subscribe to a stream:

- **Preferred:** ask the user whether they already have a WS CLI such as `wscat` (`npm i -g wscat`) or `websocat`, then drive it manually with the JSON frames above.
- **Only if the user explicitly opts in:** install a Python WS library (`pip install websockets`) on a per-session basis. Do not assume it is present.

For most agent workflows (placing orders, checking balance/positions, reading klines) the HTTP endpoints in `api-http.md` are sufficient -- WS is only needed for live push streams.
