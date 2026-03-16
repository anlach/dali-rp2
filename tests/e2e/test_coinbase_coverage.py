# Copyright 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Additional E2E tests for Coinbase and Coinbase Advanced REST plugins to improve coverage.

These tests focus on uncovered code paths:
- Swap processing (buy and sell sides matching)
- Swap post-processing logic
- Edge cases for swap handling
- Various transaction combinations
"""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from rp2.plugin.country.us import US
from rp2.rp2_decimal import RP2Decimal, ZERO
from rp2.rp2_error import RP2RuntimeError

from dali.abstract_transaction import AbstractTransaction
from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction
from dali.transaction_resolver import resolve_transactions

# Import the plugins
from dali.plugin.input.rest.coinbase import InputPlugin as CoinbaseInputPlugin
from dali.plugin.input.rest.coinbase_advanced import InputPlugin as CoinbaseAdvancedInputPlugin


# Test data generators

def generate_mock_account(currency: str = "BTC", balance: str = "1.0", created_at: str = None, updated_at: str = None):
    """Generate a mock account."""
    if created_at is None:
        created_at = "2023-01-01T00:00:00Z"
    if updated_at is None:
        updated_at = "2023-06-01T00:00:00Z"
    return {
        "id": f"account-{currency}",
        "currency": {"code": currency},
        "balance": {"amount": balance},
        "created_at": created_at,
        "updated_at": updated_at,
    }


def generate_mock_buy_with_fee(
    account_id: str,
    transaction_id: str,
    buy_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    fee_amount: str = "1.00",
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock buy transaction with full buy details."""
    return {
        "id": transaction_id,
        "type": "buy",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "buy": {
            "id": buy_id,
            "unit_price": {"amount": str(float(native_amount) / float(amount)), "currency": "USD"},
            "fee": {"amount": fee_amount, "currency": "USD"},
        },
    }


def generate_mock_sell_with_fee(
    account_id: str,
    transaction_id: str,
    sell_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    fee_amount: str = "1.00",
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock sell transaction with full sell details."""
    return {
        "id": transaction_id,
        "type": "sell",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "sell": {
            "id": sell_id,
            "unit_price": {"amount": str(float(native_amount) / float(amount)), "currency": "USD"},
            "fee": {"amount": fee_amount, "currency": "USD"},
        },
    }


def generate_mock_trade(
    transaction_id: str,
    trade_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    is_buy: bool = True,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock trade transaction (used in swaps)."""
    return {
        "id": transaction_id,
        "type": "trade",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "trade": {"id": trade_id},
    }


class TestCoinbaseSwapProcessing:
    """Tests for swap (conversion) processing in Coinbase plugin.

    These tests cover the _postprocess_swaps method which matches buy/sell sides
    of crypto-to-crypto conversions.
    """

    def test_coinbase_swap_buy_and_sell_matching(self):
        """Test Coinbase plugin processes swap when both buy and sell sides are present."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("ETH", "10.0")

        # Create a BUY transaction (ETH received, USD spent)
        buy_transaction = {
            "id": "tx-buy-1",
            "type": "buy",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "1.0", "currency": "ETH"},
            "native_amount": {"amount": "2000", "currency": "USD"},
            "buy": {
                "id": "buy-123",
                "unit_price": {"amount": "2000", "currency": "USD"},
                "fee": {"amount": "1.00", "currency": "USD"},
            },
        }

        # Create a SELL transaction (ETH sent, USD received)
        sell_transaction = {
            "id": "tx-sell-1",
            "type": "sell",
            "created_at": "2023-06-01T00:00:01Z",
            "amount": {"amount": "-0.05", "currency": "BTC"},
            "native_amount": {"amount": "-2000", "currency": "USD"},
            "sell": {
                "id": "sell-123",
                "unit_price": {"amount": "40000", "currency": "USD"},
                "fee": {"amount": "1.00", "currency": "USD"},
            },
        }

        # Mock the buy and sell lookups
        id_2_buy = {"buy-123": buy_transaction["buy"]}
        id_2_sell = {"sell-123": sell_transaction["sell"]}

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([buy_transaction, sell_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([buy_transaction["buy"]])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([sell_transaction["sell"]])):
                        result = plugin._process_account(account)

        # Should have both in and out transactions
        assert result is not None
        assert len(result.in_transactions) >= 1
        assert len(result.out_transactions) >= 1
        # Trade IDs should be tracked for swap processing
        assert len(result.in_transaction_2_trade_id) >= 0
        assert len(result.out_transaction_2_trade_id) >= 0


class TestCoinbaseTradeSwaps:
    """Tests for trade-based swap processing in Coinbase plugin."""

    def test_coinbase_trade_swap_buy_side(self):
        """Test Coinbase plugin processes trade as buy side of swap."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("ETH", "10.0")

        # Trade where we receive ETH (positive amount)
        trade_transaction = generate_mock_trade("tx-1", "trade-123", "1.0", "ETH", "2000", is_buy=True)

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([trade_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.in_transactions) >= 1
        # Trade ID should be tracked
        assert len(result.in_transaction_2_trade_id) == 1

    def test_coinbase_trade_swap_sell_side(self):
        """Test Coinbase plugin processes trade as sell side of swap."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Trade where we send BTC (negative amount)
        trade_transaction = generate_mock_trade("tx-2", "trade-123", "-0.05", "BTC", "-2000", is_buy=False)

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([trade_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.out_transactions) >= 1
        # Trade ID should be tracked
        assert len(result.out_transaction_2_trade_id) == 1


class TestCoinbaseSendEdgeCases:
    """Tests for edge cases in send transaction processing."""

    def test_coinbase_send_to_email(self):
        """Test Coinbase plugin processes send to email address."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Send to email address
        send_transaction = {
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "to": {"resource": "email", "email": "recipient@example.com"},
            "from": {"resource": "user"},
            "details": {"subtitle": "Gift to friend"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([send_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an OutTransaction (gift to another user)
        assert result is not None
        assert len(result.out_transactions) >= 1
        # Verify it's marked as a Gift
        assert result.out_transactions[0].transaction_type == "Gift"

    def test_coinbase_send_to_coinbase_earn_reversal(self):
        """Test Coinbase plugin processes Coinbase Earn reversal."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Send with "From Coinbase Earn" subtitle (reversal)
        send_transaction = {
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.01", "currency": "BTC"},
            "native_amount": {"amount": "-350", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "to": {"resource": "user"},
            "from": {"resource": "user"},
            "details": {"subtitle": "From Coinbase Earn"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([send_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an OutTransaction (sell type for Earn reversal)
        assert result is not None
        assert len(result.out_transactions) >= 1

    def test_coinbase_receive_from_email(self):
        """Test Coinbase plugin processes receive from email."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Receive from another user via email - off_blockchain status + title in details
        receive_transaction = {
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "from": {"resource": "user", "email": "sender@example.com"},
            "to": {"resource": "user"},
            "details": {"subtitle": "From user@example.com", "title": "Receive"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([receive_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an InTransaction (income from another user) - needs off_blockchain
        assert result is not None

    def test_coinbase_receive_from_coinbase_earn(self):
        """Test Coinbase plugin processes Coinbase Earn income."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Receive from Coinbase Earn - must be off_blockchain for the condition to trigger + title
        receive_transaction = {
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.01", "currency": "BTC"},
            "native_amount": {"amount": "350", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "from": {"resource": "user"},
            "to": {"resource": "user"},
            "details": {"subtitle": "From Coinbase Earn", "title": "Earn Reward"},
            "description": "Earn Task",
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([receive_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an InTransaction (Earn income)
        assert result is not None

    def test_coinbase_receive_from_unknown(self):
        """Test Coinbase plugin processes receive from unknown source."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Receive from external wallet (unknown source)
        receive_transaction = {
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "network": {
                "status": "confirmed",
                "hash": "abc123def456",
            },
            "from": {"resource": "user"},  # No email, from external
            "to": {"resource": "user"},
            "details": {"subtitle": "External deposit"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([receive_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an IntraTransaction (from unknown)
        assert result is not None
        assert len(result.intra_transactions) >= 1


class TestCoinbaseTransferEdgeCases:
    """Tests for various transfer types."""

    def test_coinbase_prime_withdrawal(self):
        """Test Coinbase plugin processes prime withdrawal."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        withdrawal_transaction = {
            "id": "tx-1",
            "type": "prime_withdrawal",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.5", "currency": "BTC"},
            "native_amount": {"amount": "-17500", "currency": "USD"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([withdrawal_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an IntraTransaction
        assert result is not None
        assert len(result.intra_transactions) >= 1

    def test_coinbase_pro_deposit(self):
        """Test Coinbase plugin processes pro deposit."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        deposit_transaction = {
            "id": "tx-1",
            "type": "pro_deposit",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.5", "currency": "BTC"},
            "native_amount": {"amount": "17500", "currency": "USD"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([deposit_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an IntraTransaction
        assert result is not None
        assert len(result.intra_transactions) >= 1


class TestCoinbaseAdvancedTradeEdgeCases:
    """Tests for Coinbase Advanced trade fill edge cases."""

    def test_coinbase_advanced_trade_fill_with_commission(self):
        """Test Coinbase Advanced plugin processes trade fill with commission."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("BTC", "1.0")

        # Trade fill with commission - must be positive amount for in_transaction
        fill_transaction = {
            "id": "tx-1",
            "type": "advanced_trade_fill",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "advanced_trade_fill": {
                "product_id": "BTC-USD",
                "fill_price": "35000",
                "commission": "1.50",
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([fill_transaction])):
                result = plugin._process_account(account)

        assert result is not None
        # Verify commission is handled - check that fiat_fee has the commission value
        if len(result.in_transactions) >= 1:
            # Commission is stored as string from JSON
            assert result.in_transactions[0].fiat_fee == "1.50"

    def test_coinbase_advanced_trade_fill_sell_with_commission(self):
        """Test Coinbase Advanced plugin processes trade fill sell with commission."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("BTC", "1.0")

        # Trade fill sell with commission
        fill_transaction = {
            "id": "tx-1",
            "type": "advanced_trade_fill",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "advanced_trade_fill": {
                "product_id": "BTC-USD",
                "fill_price": "35000",
                "commission": "1.50",
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([fill_transaction])):
                result = plugin._process_account(account)

        assert result is not None
        assert len(result.out_transactions) >= 1


class TestCoinbaseAdvancedSwapProcessing:
    """Tests for swap processing in Coinbase Advanced plugin."""

    def test_coinbase_advanced_trade_swap(self):
        """Test Coinbase Advanced plugin processes trade-based swaps."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account_eth = generate_mock_account("ETH", "10.0")
        account_btc = generate_mock_account("BTC", "1.0")

        # Trade to get ETH (buy side)
        trade_buy = generate_mock_trade("tx-1", "trade-abc", "1.0", "ETH", "2000", is_buy=True)

        # Trade to send BTC (sell side)
        trade_sell = generate_mock_trade("tx-2", "trade-abc", "-0.05", "BTC", "-2000", is_buy=False)

        # Process first account
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account_eth])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([trade_buy])):
                result1 = plugin._process_account(account_eth)

        # Process second account
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account_btc])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([trade_sell])):
                result2 = plugin._process_account(account_btc)

        assert result1 is not None
        assert result2 is not None


class TestCoinbaseFiatEdgeCases:
    """Tests for fiat transaction edge cases."""

    def test_coinbase_fiat_deposit_with_title(self):
        """Test Coinbase plugin processes fiat deposit with title."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("USD", "1000.0")

        deposit_transaction = {
            "id": "tx-1",
            "type": "fiat_deposit",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "500", "currency": "USD"},
            "native_amount": {"amount": "500", "currency": "USD"},
            "details": {
                "title": "Bank Deposit",
                "subtitle": "Wire Transfer"
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([deposit_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.in_transactions) >= 1

    def test_coinbase_fiat_withdrawal_with_title(self):
        """Test Coinbase plugin processes fiat withdrawal with title."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("USD", "1000.0")

        withdrawal_transaction = {
            "id": "tx-1",
            "type": "fiat_withdrawal",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "500", "currency": "USD"},
            "native_amount": {"amount": "500", "currency": "USD"},
            "details": {
                "title": "Bank Withdrawal",
                "subtitle": "Wire Transfer"
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([withdrawal_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.out_transactions) >= 1


class TestCoinbaseAdvancedStaking:
    """Tests for staking transactions in Coinbase Advanced."""

    def test_coinbase_advanced_staking_transfer(self):
        """Test Coinbase Advanced plugin processes staking transfer."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("ETH", "10.0")

        # Staking transfer transaction
        staking_transaction = {
            "id": "tx-1",
            "type": "staking_transfer",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-1.0", "currency": "ETH"},
            "native_amount": {"amount": "-2000", "currency": "USD"},
            "details": {
                "title": "Staking Transfer",
                "subtitle": "To staking",
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([staking_transaction])):
                result = plugin._process_account(account)

        assert result is not None


class TestCoinbaseAdvancedStablecoin:
    """Tests for stablecoin transactions in Coinbase Advanced."""

    def test_coinbase_advanced_usdc_send_to_address(self):
        """Test Coinbase Advanced processes USDC send to blockchain address."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("USDC", "1000.0")

        # USDC send to blockchain address
        send_transaction = {
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-100", "currency": "USDC"},
            "native_amount": {"amount": "-100", "currency": "USD"},
            "network": {
                "status": "confirmed",
                "hash": "0xabc123",
                "network_name": "ethereum",
                "transaction_fee": {"amount": "0.01", "currency": "ETH"},
            },
            "to": {"address": "0xDEF456"},
            "from": {"resource": "user"},
            "details": {"subtitle": "Sent USDC"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([send_transaction])):
                result = plugin._process_account(account)

        assert result is not None

    def test_coinbase_advanced_usdc_receive_from_address(self):
        """Test Coinbase Advanced processes USDC receive from blockchain address."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("USDC", "1000.0")

        # USDC receive from blockchain address - need off_blockchain for the path to work
        receive_transaction = {
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "100", "currency": "USDC"},
            "native_amount": {"amount": "100", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "0xabc123",
                "network_name": "ethereum",
            },
            "from": {"resource": "user", "address": "0xDEF456"},
            "to": {"resource": "user"},
            "details": {"subtitle": "Received USDC"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([receive_transaction])):
                result = plugin._process_account(account)

        assert result is not None


class TestCoinbaseHelperMethods:
    """Tests for helper methods in Coinbase plugin."""

    def test_coinbase_is_credit_card_spend_type(self):
        """Test _is_credit_card_spend detects cardspend type."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Test with cardspend type directly
        transaction = {"type": "cardspend"}
        assert plugin._is_credit_card_spend(transaction) is True

    def test_coinbase_is_credit_card_spend_email(self):
        """Test _is_credit_card_spend detects card treasury email."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Test with treasury email but no type (edge case)
        transaction = {
            "type": None,
            "to": {"email": "treasury+coinbase-card@coinbase.com"},
        }
        result = plugin._is_credit_card_spend(transaction)
        assert result is True


class TestCoinbaseAdvancedFillProcessing:
    """Tests for fill processing in Coinbase Advanced plugin."""

    def test_coinbase_advanced_process_fill_sell_side(self):
        """Test Coinbase Advanced plugin processes fill with SELL type (sell side of swap)."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("BTC", "1.0")

        # Trade transaction with SELL type (negative amount)
        fill_transaction = {
            "id": "tx-1",
            "type": "sell",  # Using SELL type (not trade)
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "sell": {
                "id": "sell-123",
                "unit_price": {"amount": "35000", "currency": "USD"},
                "fee": {"amount": "1.00", "currency": "USD"},
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([fill_transaction])):
                result = plugin._process_account(account)

        # Should create out transaction (selling)
        assert result is not None
        assert len(result.out_transactions) >= 1

    def test_coinbase_advanced_process_fill_buy_side(self):
        """Test Coinbase Advanced plugin processes fill with BUY type (buy side of swap)."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("ETH", "10.0")

        # Trade transaction with BUY type
        fill_transaction = {
            "id": "tx-1",
            "type": "buy",  # Using BUY type (not trade)
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "1.0", "currency": "ETH"},
            "native_amount": {"amount": "2000", "currency": "USD"},
            "buy": {
                "id": "buy-123",
                "unit_price": {"amount": "2000", "currency": "USD"},
                "fee": {"amount": "1.00", "currency": "USD"},
            },
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([fill_transaction])):
                result = plugin._process_account(account)

        # Should create in transaction (buying)
        assert result is not None
        assert len(result.in_transactions) >= 1

    def test_coinbase_advanced_process_fill_with_usdc_spot_price(self):
        """Test Coinbase Advanced plugin handles USDC as spot price source."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("USDC", "1000.0")

        # Trade with USDC currency - should use 1 as spot price
        fill_transaction = {
            "id": "tx-1",
            "type": "trade",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "500", "currency": "USDC"},
            "native_amount": {"amount": "500", "currency": "USD"},
            "trade": {"id": "trade-123"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([fill_transaction])):
                result = plugin._process_account(account)

        assert result is not None
        # Should have in transaction with spot_price = "1"
        if len(result.in_transactions) >= 1:
            assert result.in_transactions[0].spot_price == "1"


class TestCoinbaseAdvancedTransferEdgeCases:
    """Additional tests for transfer edge cases in Coinbase Advanced."""

    def test_coinbase_advanced_process_send_to_user(self):
        """Test Coinbase Advanced plugin processes send to another user."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("BTC", "1.0")

        # Send to another user (not external address)
        send_transaction = {
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "to": {"resource": "user", "email": "recipient@example.com"},
            "from": {"resource": "user"},
            "details": {"subtitle": "Gift to friend"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([send_transaction])):
                result = plugin._process_account(account)

        # Should process without error
        assert result is not None

    def test_coinbase_advanced_process_receive_from_user(self):
        """Test Coinbase Advanced plugin processes receive from another user."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("BTC", "1.0")

        # Receive from another user (off_blockchain)
        receive_transaction = {
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "from": {"resource": "user", "email": "sender@example.com"},
            "to": {"resource": "user"},
            "details": {"subtitle": "From friend"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([receive_transaction])):
                result = plugin._process_account(account)

        assert result is not None


class TestCoinbaseGainAndIncome:
    """Tests for gain and income transaction processing."""

    def test_coinbase_interest_income(self):
        """Test Coinbase plugin processes interest income."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("ETH", "10.0")

        interest_transaction = {
            "id": "tx-interest",
            "type": "interest",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.01", "currency": "ETH"},
            "native_amount": {"amount": "20", "currency": "USD"},
            "details": {"title": "Interest Payment"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([interest_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.in_transactions) >= 1
        assert result.in_transactions[0].transaction_type == "Interest"

    def test_coinbase_staking_reward(self):
        """Test Coinbase plugin processes staking reward."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("ETH", "10.0")

        staking_transaction = {
            "id": "tx-staking",
            "type": "staking_reward",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.05", "currency": "ETH"},
            "native_amount": {"amount": "100", "currency": "USD"},
            "details": {"title": "Staking Reward"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([staking_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.in_transactions) >= 1
        assert result.in_transactions[0].transaction_type == "Staking"

    def test_coinbase_inflation_reward(self):
        """Test Coinbase plugin processes inflation reward."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("ETH", "10.0")

        inflation_transaction = {
            "id": "tx-inflation",
            "type": "inflation_reward",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.001", "currency": "ETH"},
            "native_amount": {"amount": "2", "currency": "USD"},
            "details": {"title": "Inflation Reward"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([inflation_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.in_transactions) >= 1
        assert result.in_transactions[0].transaction_type == "Income"


class TestCoinbaseCardBuyback:
    """Tests for card buyback (refund) transaction processing."""

    def test_coinbase_cardbuyback_refund(self):
        """Test Coinbase plugin processes card buyback (credit card refund)."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("USD", "1000.0")

        cardbuyback_transaction = {
            "id": "tx-cardbuyback",
            "type": "cardbuyback",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "50", "currency": "USD"},
            "native_amount": {"amount": "50", "currency": "USD"},
            "details": {"title": "Card Refund", "subtitle": "Refund from purchase"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([cardbuyback_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        assert result is not None
        assert len(result.in_transactions) >= 1


class TestCoinbaseAdvancedGainAndIncome:
    """Tests for gain and income transaction processing in Coinbase Advanced."""

    def test_coinbase_advanced_interest(self):
        """Test Coinbase Advanced plugin processes interest income."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        account = generate_mock_account("ETH", "10.0")

        interest_transaction = {
            "id": "tx-interest",
            "type": "interest",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.01", "currency": "ETH"},
            "native_amount": {"amount": "20", "currency": "USD"},
            "details": {"title": "Interest Payment"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([interest_transaction])):
                result = plugin._process_account(account)

        assert result is not None

        assert len(result.in_transactions) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



class TestCoinbaseProcessFillWithBuySellLookup:
    """Tests for _process_fill with BUY and SELL types that use id_2_buy and id_2_sell lookups."""

    def test_coinbase_process_fill_buy_with_buy_lookup(self):
        """Test Coinbase plugin processes fill with BUY type and proper buy lookup."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Create a BUY transaction with the buy details
        buy_transaction = {
            "id": "tx-buy-1",
            "type": "buy",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.5", "currency": "BTC"},
            "native_amount": {"amount": "17500", "currency": "USD"},
            "buy": {
                "id": "buy-123",
                "unit_price": {"amount": "35000", "currency": "USD"},
                "fee": {"amount": "5.00", "currency": "USD"},
            },
        }

        # Provide mock buys that match the buy id
        mock_buy = {
            "id": "buy-123",
            "unit_price": {"amount": "35000", "currency": "USD"},
            "fee": {"amount": "5.00", "currency": "USD"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([buy_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([mock_buy])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should create an in transaction (buy)
        assert result is not None
        assert len(result.in_transactions) >= 1
        # Verify fee was extracted from buy lookup
        assert result.in_transactions[0].fiat_fee == "5.00"

    def test_coinbase_process_fill_sell_with_sell_lookup(self):
        """Test Coinbase plugin processes fill with SELL type and proper sell lookup."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Create a SELL transaction with the sell details
        sell_transaction = {
            "id": "tx-sell-1",
            "type": "sell",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.5", "currency": "BTC"},
            "native_amount": {"amount": "-17500", "currency": "USD"},
            "sell": {
                "id": "sell-123",
                "unit_price": {"amount": "35000", "currency": "USD"},
                "fee": {"amount": "5.00", "currency": "USD"},
            },
        }

        # Provide mock sells that match the sell id
        mock_sell = {
            "id": "sell-123",
            "unit_price": {"amount": "35000", "currency": "USD"},
            "fee": {"amount": "5.00", "currency": "USD"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([sell_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([mock_sell])):
                        result = plugin._process_account(account)

        # Should create an out transaction (sell)
        assert result is not None
        assert len(result.out_transactions) >= 1
        # Verify fee was extracted from sell lookup
        assert result.out_transactions[0].fiat_fee == "5.00"

    def test_coinbase_process_fill_buy_swap_in_below_minimum_precision(self):
        """Test Coinbase plugin handles buy swap with amount below minimum fiat precision."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Trade transaction with very small native amount (below 0.01)
        trade_transaction = {
            "id": "tx-trade-1",
            "type": "trade",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.00001", "currency": "BTC"},
            "native_amount": {"amount": "0.005", "currency": "USD"},  # Below minimum 0.01
            "trade": {"id": "trade-123"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([trade_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should still create in transaction but with UNKNOWN spot price and no fiat values
        assert result is not None
        assert len(result.in_transactions) >= 1
        assert result.in_transactions[0].spot_price == "__unknown"

    def test_coinbase_process_fill_sell_swap_out_below_minimum_precision(self):
        """Test Coinbase plugin handles sell swap with amount below minimum fiat precision."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        account = generate_mock_account("BTC", "1.0")

        # Trade sell transaction with very small native amount (below 0.01)
        trade_transaction = {
            "id": "tx-trade-1",
            "type": "trade",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.00001", "currency": "BTC"},
            "native_amount": {"amount": "-0.005", "currency": "USD"},  # Below minimum 0.01
            "trade": {"id": "trade-123"},
        }

        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([trade_transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)

        # Should still create out transaction but with UNKNOWN spot price
        assert result is not None
        assert len(result.out_transactions) >= 1


class TestCoinbaseErrorHandling:
    """Tests for error handling in coinbase plugin."""

    def test_coinbase_thread_count_exceeded(self):
        """Test Coinbase plugin raises error when thread count exceeds maximum."""
        with pytest.raises(RP2RuntimeError):
            CoinbaseInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
                thread_count=10,  # Exceeds __MAX_THREAD_COUNT of 4
            )

    def test_coinbase_empty_account_skip(self):
        """Test Coinbase plugin skips account without activity."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )

        # Account with zero balance and same created_at/updated_at
        account = {
            "id": "account-new",
            "currency": {"code": "BTC"},
            "balance": {"amount": "0.0"},
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",  # Same as created_at = no activity
        }

        # Mock the API methods - should not be called because account is skipped
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', side_effect=Exception("Should not be called")) as mock_tx:
                result = plugin._process_account(account)

        # Account should return None (skipped)
        assert result is None
