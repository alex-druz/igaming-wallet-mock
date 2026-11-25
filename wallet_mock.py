#!/usr/bin/env python3
"""iGaming wallet mock.

A small HTTP server that plays the role of an operator's seamless wallet.
A game provider calls it to authenticate a player, read the balance,
take a bet, pay a win and refund a bet.

Run:   python3 wallet_mock.py          (stop with Ctrl+C)
URL:   http://localhost:8080
Needs: Python 3.9+ only, no extra packages.

Every /wallet/* request is a POST with a JSON body and two headers:
  X-Timestamp: current Unix time in seconds
  X-Signature: hex HMAC-SHA256 of "<timestamp>.<raw body>" with the shared secret
Full API description: docs/api.md
"""
import hashlib
import hmac
import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = int(os.environ.get("WALLET_PORT", "8080"))
SECRET = os.environ.get("WALLET_SECRET", "test-secret")
MAX_CLOCK_SKEW = 300  # seconds: older or future timestamps are rejected (replay protection)

# Business errors come back with HTTP 200 and a code in the "error" field,
# the way many casino wallet APIs do it.
ERRORS = {
    0: "OK",
    1: "Insufficient funds",
    2: "Player not found",
    3: "Invalid token",
    4: "Bad request parameters",
    5: "Transaction not found",
    6: "Transaction already cancelled",
}

lock = threading.Lock()


def fresh_state():
    """Test data the server starts with (and returns to after /admin/reset)."""
    return {
        "players": {
            "player-1001": {"balance": 100.00, "currency": "EUR", "country": "MT"},
            "player-1002": {"balance": 3.00, "currency": "EUR", "country": "MT"},
            "player-1003": {"balance": 1000.00, "currency": "SEK", "country": "SE"},
        },
        "tokens": {"token-1001": "player-1001", "token-1002": "player-1002", "token-1003": "player-1003"},
        # transactionId -> what happened + the exact response we sent (for idempotency)
        "transactions": {},
        # roundId -> list of bet transactionIds in that round
        "rounds": {},
    }


state = fresh_state()


# ---------- helpers ----------

def log(message):
    print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


def reply(code, **fields):
    return {"error": code, "description": ERRORS[code], **fields}


def money(value):
    return round(float(value), 2)


def has(params, *keys):
    return all(params.get(k) not in (None, "") for k in keys)


def sign(timestamp, raw_body):
    message = f"{timestamp}.{raw_body}".encode()
    return hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()


def check_signature(headers, raw_body):
    """Returns None when the request is signed correctly, otherwise the reason."""
    timestamp = headers.get("X-Timestamp", "")
    signature = headers.get("X-Signature", "")
    if not timestamp or not signature:
        return "missing X-Timestamp or X-Signature header"
    if not timestamp.isdigit():
        return "X-Timestamp must be Unix time in seconds"
    if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW:
        return "request expired: X-Timestamp is more than 5 minutes off"
    if not hmac.compare_digest(sign(timestamp, raw_body), signature):
        return "invalid signature"
    return None


# ---------- wallet endpoints ----------

def authenticate(p):
    if not has(p, "token"):
        return reply(4)
    player_id = state["tokens"].get(p["token"])
    if not player_id:
        return reply(3)
    player = state["players"][player_id]
    return reply(0, playerId=player_id, currency=player["currency"],
                 balance=player["balance"], country=player["country"])


def balance(p):
    player = state["players"].get(p.get("playerId", ""))
    if not player:
        return reply(2)
    return reply(0, currency=player["currency"], balance=player["balance"])


def bet(p):
    if not has(p, "playerId", "roundId", "transactionId", "amount"):
        return reply(4)
    tx_id = p["transactionId"]
    known = state["transactions"].get(tx_id)
    if known:
        if known["type"] == "cancelled-before-bet":
            log(f"   -> {tx_id} was already refunded, rejecting the late bet")
            return reply(6)
        log(f"   -> {tx_id} already processed, returning the same response (no second charge)")
        return known["response"]
    player = state["players"].get(p["playerId"])
    if not player:
        return reply(2)
    try:
        amount = money(p["amount"])
    except ValueError:
        return reply(4)
    if amount <= 0:
        return reply(4)
    if player["balance"] < amount:
        return reply(1, balance=player["balance"])
    player["balance"] = money(player["balance"] - amount)
    response = reply(0, transactionId=tx_id, currency=player["currency"], balance=player["balance"])
    state["transactions"][tx_id] = {"type": "bet", "playerId": p["playerId"], "roundId": p["roundId"],
                                    "amount": amount, "refunded": False, "response": response}
    state["rounds"].setdefault(p["roundId"], []).append(tx_id)
    return response


def win(p):
    if not has(p, "playerId", "roundId", "transactionId", "amount"):
        return reply(4)
    tx_id = p["transactionId"]
    known = state["transactions"].get(tx_id)
    if known:
        log(f"   -> {tx_id} already processed, returning the same response (no second payout)")
        return known["response"]
    player = state["players"].get(p["playerId"])
    if not player:
        return reply(2)
    if p["roundId"] not in state["rounds"]:
        log(f"   -> no bet in round {p['roundId']}, rejecting the win")
        return reply(5)
    try:
        amount = money(p["amount"])
    except ValueError:
        return reply(4)
    if amount < 0:
        return reply(4)
    player["balance"] = money(player["balance"] + amount)
    response = reply(0, transactionId=tx_id, currency=player["currency"], balance=player["balance"])
    state["transactions"][tx_id] = {"type": "win", "playerId": p["playerId"], "roundId": p["roundId"],
                                    "amount": amount, "response": response}
    return response


def refund(p):
    """Cancels a bet. transactionId is the id of the bet to refund."""
    if not has(p, "playerId", "transactionId"):
        return reply(4)
    tx_id = p["transactionId"]
    player = state["players"].get(p["playerId"])
    if not player:
        return reply(2)
    known = state["transactions"].get(tx_id)
    if known is None:
        # We never saw this bet (for example it timed out on the way to us).
        # Answer OK and remember it, so a late bet with this id is rejected.
        log(f"   -> bet {tx_id} not found: refund OK without balance change, a late bet will be rejected")
        response = reply(0, transactionId=tx_id, currency=player["currency"], balance=player["balance"])
        state["transactions"][tx_id] = {"type": "cancelled-before-bet", "playerId": p["playerId"],
                                        "amount": 0, "response": response}
        return response
    if known["type"] != "bet":
        return reply(4)
    if known["refunded"]:
        log(f"   -> bet {tx_id} already refunded, balance unchanged")
    else:
        player["balance"] = money(player["balance"] + known["amount"])
        known["refunded"] = True
        log(f"   -> returning {known['amount']} for bet {tx_id}")
    return reply(0, transactionId=tx_id, currency=player["currency"], balance=player["balance"])


ROUTES = {
    "/wallet/authenticate": authenticate,
    "/wallet/balance": balance,
    "/wallet/bet": bet,
    "/wallet/win": win,
    "/wallet/refund": refund,
}


# ---------- HTTP layer ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # we print our own, shorter log lines

    def send(self, status, body):
        data = json.dumps(body, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            log("   -> client already closed the connection (timeout), but the operation WAS done")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            return self.send(200, {"status": "ok", "endpoints": sorted(ROUTES)})
        if path == "/admin/state":
            view = {k: v for k, v in state.items() if k != "tokens"}
            view["transactions"] = {tx: {k: v for k, v in rec.items() if k != "response"}
                                    for tx, rec in state["transactions"].items()}
            return self.send(200, view)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        global state
        path = urlparse(self.path).path
        raw_body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()

        if path == "/admin/reset":
            with lock:
                state = fresh_state()
            log("POST /admin/reset -> state reset")
            return self.send(200, {"status": "reset"})

        if path == "/debug/signature":
            # Helper for learning: shows what the server would sign for this body.
            timestamp = self.headers.get("X-Timestamp") or str(int(time.time()))
            return self.send(200, {"timestamp": timestamp,
                                   "stringToSign": f"{timestamp}.{raw_body}",
                                   "expectedSignature": sign(timestamp, raw_body),
                                   "receivedSignature": self.headers.get("X-Signature")})

        handler = ROUTES.get(path)
        if not handler:
            return self.send(404, {"error": "not found"})

        simulate = (self.headers.get("X-Simulate") or "").lower()
        log(f"POST {path} {raw_body}" + (f"  [X-Simulate: {simulate}]" if simulate else ""))

        problem = check_signature(self.headers, raw_body)
        if problem:
            log(f"   -> 401: {problem}")
            return self.send(401, {"error": "unauthorized", "description": problem})

        try:
            params = json.loads(raw_body or "{}")
            if not isinstance(params, dict):
                raise ValueError
        except ValueError:
            log("   -> 400: body is not a JSON object")
            return self.send(400, {"error": "bad_request", "description": "body must be a JSON object"})
        params = {k: str(v) for k, v in params.items()}

        if simulate == "error500":
            log("   -> 500, nothing processed")
            return self.send(500, {"error": "internal_error"})

        with lock:
            result = handler(params)
        log(f"   -> error={result['error']} {result['description']}"
            + (f" balance={result['balance']}" if "balance" in result else ""))

        if simulate == "timeout":
            log("   -> processed, holding the response for 6 s")
            time.sleep(6)
        elif simulate == "slow":
            time.sleep(2)
        self.send(200, result)


if __name__ == "__main__":
    print(f"Wallet mock on http://localhost:{PORT}  (secret: {SECRET}, stop: Ctrl+C)", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
