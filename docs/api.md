# Wallet mock API

Base URL: `http://localhost:8080`

## Signing requests

Every `/wallet/*` request is a `POST` with a JSON body and two headers:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Timestamp` | Current Unix time in seconds, e.g. `1764064800` |
| `X-Signature` | Hex HMAC-SHA256 of `<timestamp>.<raw body>` with the shared secret |

The secret is `test-secret` (change it with the `WALLET_SECRET` environment variable).

Example: body `{"token": "token-1001"}` sent at `1764064800`
→ string to sign: `1764064800.{"token": "token-1001"}`
→ `X-Signature` = HMAC-SHA256 of that string with `test-secret`.

The server signs the **raw body exactly as received**. If you sign a pretty-printed body and send a
one-line body (or the other way round), the signature will not match.

Replay protection: a timestamp more than **5 minutes** away from the server clock is rejected,
so a captured request cannot be sent again later.

Signature problems return **HTTP 401**:

```json
{ "error": "unauthorized", "description": "invalid signature" }
```

Need to debug a signature? `POST /debug/signature` with the same body and `X-Timestamp`
returns the string the server signs and the signature it expects. No signature needed for this call.

## Response format

Business results come back with **HTTP 200** and a code in the `error` field:

| `error` | `description` |
|---|---|
| 0 | OK |
| 1 | Insufficient funds |
| 2 | Player not found |
| 3 | Invalid token |
| 4 | Bad request parameters |
| 5 | Transaction not found |
| 6 | Transaction already cancelled |

Other HTTP statuses: `400` body is not a JSON object, `401` signature problem, `404` unknown path,
`500` simulated server error.

## Endpoints

### `POST /wallet/authenticate`
Exchanges the launch token for the player.

| Field | Required | Example |
|---|---|---|
| `token` | yes | `token-1001` |

Response: `playerId`, `currency`, `balance`, `country`.

### `POST /wallet/balance`

| Field | Required | Example |
|---|---|---|
| `playerId` | yes | `player-1001` |

Response: `currency`, `balance`.

### `POST /wallet/bet`
Takes money from the player.

| Field | Required | Example |
|---|---|---|
| `playerId` | yes | `player-1001` |
| `roundId` | yes | `round-1` |
| `transactionId` | yes | `round-1-bet` |
| `amount` | yes, > 0 | `2.50` |

Response: `transactionId`, `currency`, `balance` (after the bet).

### `POST /wallet/win`
Pays a win. The round must already have a bet, otherwise `error: 5`. `amount` can be `0` (a losing round).

Fields as for `bet`, with its own `transactionId`.

### `POST /wallet/refund`
Cancels a bet and returns its amount. `transactionId` is the **bet's** id.

| Field | Required | Example |
|---|---|---|
| `playerId` | yes | `player-1001` |
| `transactionId` | yes | `round-1-bet` |

## Rules worth testing

- **Idempotency.** The same `transactionId` sent twice is processed once. The second call returns the
  first response and does not charge or pay again. This is what makes retries after a timeout safe.
- **Refund twice** returns OK and does not change the balance again.
- **Refund before the bet.** A refund for a bet the wallet never saw returns OK with no balance change,
  and a bet that arrives later with that `transactionId` is rejected with `error: 6`.
- **Win without a bet** in the round is rejected with `error: 5`.

## Failure simulation

Add the `X-Simulate` header to any `/wallet/*` call (it is not part of the signature):

| Value | What happens |
|---|---|
| `timeout` | The request **is processed**, but the response comes after 6 s, so a client with a 5 s timeout gives up |
| `slow` | Response after 2 s |
| `error500` | HTTP 500, nothing is processed |

`timeout` is the interesting one: the client thinks the bet failed, but the money is already taken.
The right reaction is a retry with the same `transactionId` or a refund.

## Service endpoints (no signature)

| Call | What it does |
|---|---|
| `GET /health` | Status and the list of endpoints |
| `GET /admin/state` | Players, balances and all transactions |
| `POST /admin/reset` | Back to the starting test data |
| `POST /debug/signature` | Shows the expected signature for a body |

## Test data

| Token | Player | Balance | Country |
|---|---|---|---|
| `token-1001` | `player-1001` | 100.00 EUR | MT |
| `token-1002` | `player-1002` | 3.00 EUR | MT |
| `token-1003` | `player-1003` | 1000.00 SEK | SE |
