# igaming-wallet-mock

A mock **seamless wallet API** for practising iGaming integration testing.

In a seamless wallet integration the player's money stays with the casino operator.
The game provider calls the operator's wallet on every step of a game round:
authenticate the player, take the bet, pay the win, refund the bet if something went wrong.
This project is a small version of that wallet, so the tricky parts can be tested on a laptop:
signed requests, retries, timeouts and refunds.

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

## Why I built it

I decided to build a small example of what I do every day at work: testing game integrations with
casino operators. Building it myself helps me understand the technical details better, and the important
errors that can happen in this work: timeouts, duplicate requests, refunds that arrive before the bet.
Understanding them is what lets me give platforms and players the best service, and prevent these errors
before they reach production.
I designed the scenarios from real integration cases and built the code with an AI coding assistant.

## Quick start

```bash
python3 wallet_mock.py
```

In a second terminal tab, play one round (authenticate → bet → retry → win):

```bash
python3 examples/play_round.py
```

The server terminal shows every request and what the wallet did with it.

## What it covers

| Topic | How |
|---|---|
| **Request signing** | HMAC-SHA256 of `timestamp.body` in the `X-Signature` header |
| **Replay protection** | Requests with a timestamp older than 5 minutes are rejected |
| **Idempotency** | The same `transactionId` is processed only once; retries return the first response |
| **Refunds** | Refund twice, refund before the bet, late bet after a refund |
| **Failure simulation** | `X-Simulate: timeout`, `slow` or `error500` |
| **Debugging** | `/debug/signature` shows what the server signs; `/admin/state` shows all balances and transactions |

Full API description: [docs/api.md](docs/api.md)

## Example: a bet with curl

```bash
BODY='{"playerId": "player-1001", "roundId": "round-1", "transactionId": "round-1-bet", "amount": 2}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "test-secret" | awk '{print $NF}')

curl -s http://localhost:8080/wallet/bet \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: $SIG" \
  -d "$BODY"
```

Run it twice: the second call returns the same balance, because the bet with `round-1-bet` was already taken.

## Project structure

```
wallet_mock.py         the server (Python standard library only)
examples/play_round.py one game round as a provider would play it
docs/api.md            API description, error codes, rules worth testing
```

## Roadmap

- [x] Seamless wallet: authenticate, balance, bet, win, refund
- [x] HMAC signature with replay protection
- [x] Idempotency and refund edge cases
- [x] Timeout / slow / 500 simulation
- [ ] Automated tests with pytest
- [ ] Dockerfile
- [ ] Postman collection with signing in a pre-request script (separate repo: `api-testing-postman`)
- [ ] Playwright API tests in TypeScript (separate repo: `playwright-tests`)
- [ ] Same `transactionId` with a different amount should be rejected
- [ ] Balance transfer model (money moved into the provider's wallet)

## Note

All players, tokens and data here are made up. This is a learning project and is not based on
any company's real API.
