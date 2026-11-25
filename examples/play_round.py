#!/usr/bin/env python3
"""Plays one game round against the wallet mock, the way a game provider would.

Start the mock first:   python3 wallet_mock.py
Then in another tab:    python3 examples/play_round.py

Steps: authenticate -> balance -> bet -> same bet again (retry) -> win -> refund
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("WALLET_URL", "http://localhost:8080")
SECRET = os.environ.get("WALLET_SECRET", "test-secret")


def call(path, body):
    raw = json.dumps(body)
    timestamp = str(int(time.time()))
    signature = hmac.new(SECRET.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        BASE_URL + path,
        data=raw.encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Timestamp": timestamp, "X-Signature": signature},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        result = {"httpStatus": error.code, **json.load(error)}
    print(f"POST {path} {raw}\n  <- {json.dumps(result)}\n")
    return result


if __name__ == "__main__":
    round_id = f"round-{int(time.time())}"
    bet_id = f"{round_id}-bet"

    player = call("/wallet/authenticate", {"token": "token-1001"})
    player_id = player["playerId"]
    start = call("/wallet/balance", {"playerId": player_id})["balance"]

    after_bet = call("/wallet/bet", {"playerId": player_id, "roundId": round_id,
                                     "transactionId": bet_id, "amount": 2})["balance"]
    retry = call("/wallet/bet", {"playerId": player_id, "roundId": round_id,
                                 "transactionId": bet_id, "amount": 2})["balance"]
    after_win = call("/wallet/win", {"playerId": player_id, "roundId": round_id,
                                     "transactionId": f"{round_id}-win", "amount": 5})["balance"]

    print("Checks:")
    print(f"  bet took 2:           {start} -> {after_bet}  {'OK' if round(start - 2, 2) == after_bet else 'FAIL'}")
    print(f"  retry did not charge: {after_bet} -> {retry}  {'OK' if retry == after_bet else 'FAIL'}")
    print(f"  win paid 5:           {retry} -> {after_win}  {'OK' if round(retry + 5, 2) == after_win else 'FAIL'}")
