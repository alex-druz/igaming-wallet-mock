def test_bet_takes_money_from_balance(wallet):
    """A successful bet takes the amount from the player's balance."""
    # Arrange: a 2 EUR bet for a player with 100 EUR
    bet = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 2}

    # Act: place the bet
    result = wallet.call("/wallet/bet", bet)

    # Assert: the bet is accepted and 2 EUR are taken
    assert result["httpStatus"] == 200
    assert result["error"] == 0
    assert result["balance"] == 98.0


def test_bet_retry_does_not_charge_twice(wallet):
    """A retried bet with the same transactionId is not charged a second time."""
    # Arrange: a 2 EUR bet for a player with 100 EUR
    bet = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 2}

    # Act: place the bet
    first = wallet.call("/wallet/bet", bet)

    # Assert: the first bet is accepted and 2 EUR are taken
    assert first["httpStatus"] == 200
    assert first["error"] == 0
    assert first["balance"] == 98.0

    # Act: send the same bet again, as a provider does after a timeout
    retry = wallet.call("/wallet/bet", bet)

    # Assert: the retry is accepted, but the balance is still 98, not 96
    assert retry["httpStatus"] == 200
    assert retry["error"] == 0
    assert retry["balance"] == 98.0


def test_bet_with_insufficient_funds_is_rejected(wallet):
    """A bet bigger than the balance is rejected and the balance does not change."""
    # Arrange: a 50 EUR bet for a player with only 3 EUR
    bet = {"playerId": "player-1002", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 50}

    # Act: place the bet
    result = wallet.call("/wallet/bet", bet)

    # Assert: business error 1 "Insufficient funds" comes with HTTP 200, balance stays 3
    assert result["httpStatus"] == 200
    assert result["error"] == 1
    assert result["balance"] == 3.0


def test_request_with_wrong_signature_is_rejected(wallet):
    """A request with a wrong signature is rejected before the wallet processes it."""
    # Arrange: a normal balance request
    body = {"playerId": "player-1001"}

    # Act: send it with a broken signature
    result = wallet.call("/wallet/balance", body, signature="wrong")

    # Assert: HTTP 401, the wallet refuses it before doing anything
    assert result["httpStatus"] == 401
    assert result["error"] == "unauthorized"
    assert result["description"] == "invalid signature"


def test_win_adds_money_to_balance(wallet):
    """A win after a bet adds the win amount to the player's balance."""
    # Arrange: a 2 EUR bet, so the round exists
    bet = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 2}
    wallet.call("/wallet/bet", bet)

    # Act: pay a 5 EUR win in the same round
    win = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-win", "amount": 5}
    result = wallet.call("/wallet/win", win)

    # Assert: the win is accepted, balance is 100 - 2 + 5
    assert result["httpStatus"] == 200
    assert result["error"] == 0
    assert result["balance"] == 103.0


def test_win_without_bet_is_rejected(wallet):
    """A win in a round that has no bet is rejected and no money is paid."""
    # Arrange: a 5 EUR win for a round where no bet was placed
    win = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-win", "amount": 5}

    # Act: pay the win
    result = wallet.call("/wallet/win", win)

    # Assert: business error 5 "Transaction not found" comes with HTTP 200
    assert result["httpStatus"] == 200
    assert result["error"] == 5

    # Assert: the balance is still 100, nothing was paid
    balance = wallet.call("/wallet/balance", {"playerId": "player-1001"})
    assert balance["balance"] == 100.0


def test_refund_twice_returns_money_once(wallet):
    """Refunding the same bet twice returns the money only once."""
    # Arrange: a 2 EUR bet for a player with 100 EUR
    bet = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 2}
    wallet.call("/wallet/bet", bet)
    refund = {"playerId": "player-1001", "transactionId": "round-1-bet"}

    # Act: refund the bet
    first = wallet.call("/wallet/refund", refund)

    # Assert: the 2 EUR are back
    assert first["httpStatus"] == 200
    assert first["error"] == 0
    assert first["balance"] == 100.0

    # Act: send the same refund again
    second = wallet.call("/wallet/refund", refund)

    # Assert: still OK, but the balance is 100, not 102
    assert second["httpStatus"] == 200
    assert second["error"] == 0
    assert second["balance"] == 100.0


def test_refund_before_bet_rejects_late_bet(wallet):
    """A refund for a bet the wallet never saw blocks that bet if it arrives later."""
    # Arrange: a refund for a bet that has not reached the wallet yet
    refund = {"playerId": "player-1001", "transactionId": "round-1-bet"}

    # Act: send the refund first
    result = wallet.call("/wallet/refund", refund)

    # Assert: the refund is OK, the balance does not change
    assert result["httpStatus"] == 200
    assert result["error"] == 0
    assert result["balance"] == 100.0

    # Act: the late bet with the same transactionId arrives
    bet = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 2}
    late_bet = wallet.call("/wallet/bet", bet)

    # Assert: business error 6 "Transaction already cancelled", no money is taken
    assert late_bet["httpStatus"] == 200
    assert late_bet["error"] == 6
    balance = wallet.call("/wallet/balance", {"playerId": "player-1001"})
    assert balance["balance"] == 100.0


def test_request_with_expired_timestamp_is_rejected(wallet):
    """A correctly signed request with an old timestamp is rejected (replay protection)."""
    # Arrange: a normal balance request
    body = {"playerId": "player-1001"}

    # Act: send it signed with a timestamp from 2001
    result = wallet.call("/wallet/balance", body, timestamp=1000000000)

    # Assert: HTTP 401, the request is too old
    assert result["httpStatus"] == 401
    assert result["error"] == "unauthorized"
    assert "request expired" in result["description"]


def test_bet_after_timeout_is_taken_and_retry_is_safe(wallet):
    """A bet that times out is still taken, and a retry does not charge again."""
    # Arrange: a 2 EUR bet for a player with 100 EUR
    bet = {"playerId": "player-1001", "roundId": "round-1",
           "transactionId": "round-1-bet", "amount": 2}

    # Act: place the bet, the wallet answers only after 6 seconds
    wallet.call("/wallet/bet", bet, headers={"X-Simulate": "timeout"})

    # Assert: the money is already taken
    balance = wallet.call("/wallet/balance", {"playerId": "player-1001"})
    assert balance["balance"] == 98.0

    # Act: the provider retries the same bet
    retry = wallet.call("/wallet/bet", bet)

    # Assert: the retry is accepted, the balance is still 98, not 96
    assert retry["httpStatus"] == 200
    assert retry["error"] == 0
    assert retry["balance"] == 98.0