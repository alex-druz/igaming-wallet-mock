"""Shared setup for the tests.

pytest loads this file automatically. Fixtures defined here can be used by any test
just by naming them as a parameter, e.g. `def test_something(wallet):`.
"""
import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

import wallet_mock


class WalletClient:
    """Sends signed requests to the wallet, the way a game provider would."""

    def __init__(self, base_url, secret="test-secret"):
        self.base_url = base_url
        self.secret = secret

    def call(self, path, body, timestamp=None, signature=None, headers=None):
        """POST a JSON body to the wallet and return the JSON answer.

        By default the request is signed correctly. Pass `timestamp` or `signature`
        to send a broken one on purpose. The HTTP status is added as "httpStatus".
        """
        raw = json.dumps(body)
        timestamp = str(timestamp if timestamp is not None else int(time.time()))
        if signature is None:
            message = f"{timestamp}.{raw}".encode()
            signature = hmac.new(self.secret.encode(), message, hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            self.base_url + path,
            data=raw.encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Timestamp": timestamp,
                     "X-Signature": signature, **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return {"httpStatus": response.status, **json.load(response)}
        except urllib.error.HTTPError as error:
            return {"httpStatus": error.code, **json.load(error)}


@pytest.fixture(scope="session")
def base_url():
    """Starts the wallet once for the whole test run, on a free port."""
    server = wallet_mock.ThreadingHTTPServer(("127.0.0.1", 0), wallet_mock.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def wallet(base_url):
    """A client for a wallet with fresh test data, so tests don't affect each other."""
    wallet_mock.state = wallet_mock.fresh_state()
    return WalletClient(base_url)
