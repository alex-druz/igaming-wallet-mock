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
