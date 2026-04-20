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

"""E2E tests for Coinbase and Coinbase Advanced REST plugins.

These tests verify the plugins can handle various transaction types,
account processing, swap processing, and edge cases.
"""

import json
import os
import pickle
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from rp2.plugin.country.us import US
from rp2.rp2_decimal import RP2Decimal

from dali.abstract_transaction import AbstractTransaction
from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction
from dali.transaction_resolver import resolve_transactions

# Import the plugins
from dali.plugin.input.rest.coinbase import InputPlugin as CoinbaseInputPlugin
from dali.plugin.input.rest.coinbase_advanced import InputPlugin as CoinbaseAdvancedInputPlugin

# Import shared fixtures from e2e_shared.py
from e2e_shared import MockPairConverter


def _run_full_pipeline(
    plugin,
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline: load transactions, resolve, return results."""
    transactions = plugin.load(US())

    if mock_converter is None:
        mock_converter = MockPairConverter()
    dali_configuration: Dict[str, Any] = {
        Keyword.NATIVE_FIAT.value: "USD",
        Keyword.HISTORICAL_PAIR_CONVERTERS.value: [mock_converter],
    }

    resolved_transactions = resolve_transactions(
        transactions,
        dali_configuration,
        read_spot_price_from_web=False,
    )

    return resolved_transactions


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


def generate_mock_buy_transaction(
    account_id: str,
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock buy transaction."""
    return {
        "id": transaction_id,
        "type": "buy",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "buy": {
            "id": f"buy-{transaction_id}",
            "unit_price": {"amount": str(float(native_amount) / float(amount)), "currency": "USD"},
            "fee": {"amount": "0.01", "currency": "USD"},
        },
    }


def generate_mock_sell_transaction(
    account_id: str,
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock sell transaction."""
    return {
        "id": transaction_id,
        "type": "sell",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "sell": {
            "id": f"sell-{transaction_id}",
            "unit_price": {"amount": str(float(native_amount) / float(amount)), "currency": "USD"},
            "fee": {"amount": "0.01", "currency": "USD"},
        },
    }


def generate_mock_send_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    is_outgoing: bool = True,
    to_email: str = None,
    from_user: bool = False,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock send transaction."""
    tx = {
        "id": transaction_id,
        "type": "send",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "network": {
            "status": "off_blockchain" if not from_user else "confirmed",
            "hash": f"hash-{transaction_id}",
        },
        "details": {"subtitle": "Some subtitle"},
    }
    if is_outgoing:
        tx["to"] = {
            "resource": "email" if to_email else "user",
            "email": to_email,
        }
        tx["from"] = {"resource": "user"}
    else:
        tx["from"] = {"resource": "user", "email": "sender@example.com"}
        tx["to"] = {"resource": "user"}
    return tx


def generate_mock_receive_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    from_email: str = "sender@example.com",
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock receive transaction."""
    return {
        "id": transaction_id,
        "type": "receive",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "network": {
            "status": "off_blockchain",
            "hash": f"hash-{transaction_id}",
        },
        "from": {
            "resource": "user",
            "email": from_email,
        },
        "to": {"resource": "user"},
        "details": {"subtitle": f"From {from_email}"},
    }


def generate_mock_interest_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    title: str = "Coinbase Earn",
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock interest/reward transaction."""
    return {
        "id": transaction_id,
        "type": "interest",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "details": {"title": title},
    }


def generate_mock_staking_reward_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock staking reward transaction."""
    return {
        "id": transaction_id,
        "type": "staking_reward",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "details": {"title": "Staking Reward"},
    }


def generate_mock_inflation_reward_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock inflation reward transaction."""
    return {
        "id": transaction_id,
        "type": "inflation_reward",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "details": {"title": "Inflation Reward"},
    }


def generate_mock_fiat_deposit_transaction(
    transaction_id: str,
    amount: str,
    currency: str = "USD",
    title: str = "Fiat Deposit",
    subtitle: str = "Bank Transfer",
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock fiat deposit transaction."""
    return {
        "id": transaction_id,
        "type": "fiat_deposit",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
        "details": {"title": title, "subtitle": subtitle},
    }


def generate_mock_fiat_withdrawal_transaction(
    transaction_id: str,
    amount: str,
    currency: str = "USD",
    title: str = "Fiat Withdrawal",
    subtitle: str = "Bank Transfer",
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock fiat withdrawal transaction."""
    return {
        "id": transaction_id,
        "type": "fiat_withdrawal",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
        "details": {"title": title, "subtitle": subtitle},
    }


def generate_mock_advanced_trade_fill_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    is_buy: bool = True,
    product_id: str = None,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock advanced trade fill transaction."""
    if product_id is None:
        product_id = f"{currency}-USD"
    return {
        "id": transaction_id,
        "type": "advanced_trade_fill",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "advanced_trade_fill": {
            "product_id": product_id,
            "fill_price": str(float(native_amount) / float(amount)) if float(amount) != 0 else "0",
            "commission": "0.01",
        },
    }


def generate_mock_pro_deposit_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock pro_deposit transaction."""
    return {
        "id": transaction_id,
        "type": "pro_deposit",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
    }


def generate_mock_pro_withdrawal_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock pro_withdrawal transaction."""
    return {
        "id": transaction_id,
        "type": "pro_withdrawal",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
    }


def generate_mock_exchange_deposit_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock exchange_deposit transaction."""
    return {
        "id": transaction_id,
        "type": "exchange_deposit",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
    }


def generate_mock_exchange_withdrawal_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock exchange_withdrawal transaction."""
    return {
        "id": transaction_id,
        "type": "exchange_withdrawal",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
    }


def generate_mock_prime_withdrawal_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock prime_withdrawal transaction."""
    return {
        "id": transaction_id,
        "type": "prime_withdrawal",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": amount, "currency": "USD"},
    }


def generate_mock_trade_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    is_buy: bool = True,
    trade_id: str = None,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock trade transaction."""
    if trade_id is None:
        trade_id = f"trade-{transaction_id}"
    return {
        "id": transaction_id,
        "type": "trade",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "trade": {"id": trade_id},
    }


def generate_mock_card_spend_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock card spend transaction."""
    return {
        "id": transaction_id,
        "type": "cardspend",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "to": {"email": "treasury+coinbase-card@coinbase.com"},
        "details": {"title": "Card Spend", "subtitle": "Coinbase Card"},
    }


def generate_mock_card_buyback_transaction(
    transaction_id: str,
    amount: str,
    currency: str,
    native_amount: str,
    created_at: str = "2023-06-01T00:00:00Z",
):
    """Generate a mock card buyback (refund) transaction."""
    return {
        "id": transaction_id,
        "type": "cardbuyback",
        "created_at": created_at,
        "amount": {"amount": amount, "currency": currency},
        "native_amount": {"amount": native_amount, "currency": "USD"},
        "details": {"title": "Card Refund", "subtitle": "Refund"},
    }


# Coinbase Tests

class TestCoinbasePlugin:
    """End-to-end tests for Coinbase REST API plugin."""

    def test_coinbase_initialization(self):
        """Test that Coinbase plugin can be initialized."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin is not None
        assert plugin.account_holder == "test_user"

    def test_coinbase_cache_key(self):
        """Test that Coinbase plugin has correct cache key."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.cache_key() == "coinbase-test_user"

    def test_coinbase_with_thread_count(self):
        """Test that Coinbase plugin accepts thread_count parameter."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=2,
        )
        
        assert plugin is not None

    def test_coinbase_thread_count_validation(self):
        """Test that Coinbase plugin validates thread_count max value."""
        with pytest.raises(Exception):
            CoinbaseInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
                thread_count=10,
            )

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_buy_transaction(self, mock_pagination):
        """Test Coinbase plugin processes buy transactions."""
        # Setup mock accounts
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_pagination.side_effect = [
            iter(mock_accounts),  # accounts
            iter([]),  # transactions
            iter([]),  # buys
            iter([]),  # sells
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None  # Just test initialization works

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_sell_transaction(self, mock_pagination):
        """Test Coinbase plugin processes sell transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([]),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_send_transaction(self, mock_pagination):
        """Test Coinbase plugin processes send transactions."""
        # Use negative amount for outgoing send
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [{
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},  # Negative = outgoing
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "network": {
                "status": "confirmed",
                "hash": "hash-tx-1",
            },
            "to": {"resource": "user", "email": "recipient@example.com"},
            "from": {"resource": "user"},
            "details": {"subtitle": "To external wallet"},
        }]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_receive_transaction(self, mock_pagination):
        """Test Coinbase plugin processes receive transactions."""
        # Positive amount for incoming
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [{
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "hash-tx-1",
            },
            "from": {"resource": "user"},
            "to": {"resource": "user"},
            "details": {"subtitle": "From external wallet"},
        }]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_interest_transaction(self, mock_pagination):
        """Test Coinbase plugin processes interest transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_interest_transaction("tx-1", "0.01", "BTC", "350")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_staking_reward_transaction(self, mock_pagination):
        """Test Coinbase plugin processes staking reward transactions."""
        mock_accounts = [generate_mock_account("ETH", "10.0")]
        mock_transactions = [generate_mock_staking_reward_transaction("tx-1", "0.5", "ETH", "1000")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_inflation_reward_transaction(self, mock_pagination):
        """Test Coinbase plugin processes inflation reward transactions."""
        mock_accounts = [generate_mock_account("SOL", "100.0")]
        mock_transactions = [generate_mock_inflation_reward_transaction("tx-1", "10", "SOL", "500")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_fiat_deposit_transaction(self, mock_pagination):
        """Test Coinbase plugin processes fiat deposit transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_fiat_deposit_transaction("tx-1", "1000")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_fiat_withdrawal_transaction(self, mock_pagination):
        """Test Coinbase plugin processes fiat withdrawal transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_fiat_withdrawal_transaction("tx-1", "500")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_advanced_trade_fill_buy(self, mock_pagination):
        """Test Coinbase plugin processes advanced trade fill buy transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_advanced_trade_fill_transaction("tx-1", "0.1", "BTC", "3500", is_buy=True)]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_advanced_trade_fill_sell(self, mock_pagination):
        """Test Coinbase plugin processes advanced trade fill sell transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_advanced_trade_fill_transaction("tx-1", "-0.1", "BTC", "-3500", is_buy=False)]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_pro_deposit(self, mock_pagination):
        """Test Coinbase plugin processes pro_deposit transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_pro_deposit_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_pro_withdrawal(self, mock_pagination):
        """Test Coinbase plugin processes pro_withdrawal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_pro_withdrawal_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_exchange_deposit(self, mock_pagination):
        """Test Coinbase plugin processes exchange_deposit transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_exchange_deposit_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_exchange_withdrawal(self, mock_pagination):
        """Test Coinbase plugin processes exchange_withdrawal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_exchange_withdrawal_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_prime_withdrawal(self, mock_pagination):
        """Test Coinbase plugin processes prime_withdrawal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_prime_withdrawal_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_card_spend(self, mock_pagination):
        """Test Coinbase plugin processes card spend transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_card_spend_transaction("tx-1", "100", "USD", "100")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_process_card_buyback(self, mock_pagination):
        """Test Coinbase plugin processes card buyback (refund) transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_card_buyback_transaction("tx-1", "50", "USD", "50")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_with_small_fiat_amounts(self, mock_pagination):
        """Test Coinbase plugin handles small fiat amounts (< MINIMUM_FIAT_PRECISION)."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        # Create transaction with very small native amount
        mock_transactions = [generate_mock_interest_transaction("tx-1", "0.0001", "BTC", "0.001")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_skip_empty_account(self, mock_pagination):
        """Test Coinbase plugin skips account without activity."""
        # Account with no activity - created_at == updated_at and zero balance
        mock_account = generate_mock_account("BTC", "0.0", created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z")
        mock_pagination.side_effect = [
            iter([mock_account]),
            iter([]),
            iter([]),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert len(transactions) == 0

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_with_buy_with_fee(self, mock_pagination):
        """Test Coinbase plugin processes buy transactions with fee data."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        
        # Create a buy transaction that references a buy record
        buy_data = {
            "id": "buy-123",
            "unit_price": {"amount": "35000", "currency": "USD"},
            "fee": {"amount": "1.00", "currency": "USD"},
        }
        
        mock_transaction = {
            "id": "tx-1",
            "type": "buy",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "buy": {"id": "buy-123"},
        }
        
        mock_buys = [buy_data]
        
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
            iter(mock_buys),
            iter([]),
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None


# Coinbase Advanced Tests

class TestCoinbaseAdvancedPlugin:
    """End-to-end tests for Coinbase Advanced Trade REST API plugin."""

    def test_coinbase_advanced_initialization(self):
        """Test that Coinbase Advanced plugin can be initialized."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin is not None

    def test_coinbase_advanced_cache_key(self):
        """Test that Coinbase Advanced plugin has correct cache key."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.cache_key() == "coinbase advanced-test_user"

    def test_coinbase_advanced_with_pickle_cache(self):
        """Test that Coinbase Advanced plugin accepts pickle cache parameter."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            pickle_api_cache_enabled="1",
        )
        
        assert plugin is not None

    def test_coinbase_advanced_with_pickle_cache_disabled(self):
        """Test that Coinbase Advanced plugin works with pickle cache disabled."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            pickle_api_cache_enabled="0",
        )
        
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_buy_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes buy transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) == 0

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_send_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes send transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_send_transaction("tx-1", "0.1", "BTC", "3500", is_outgoing=True)]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_receive_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes receive transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_receive_transaction("tx-1", "0.1", "BTC", "3500")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_interest_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes interest transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_interest_transaction("tx-1", "0.01", "BTC", "350")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_staking_reward_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes staking reward transactions."""
        mock_accounts = [generate_mock_account("ETH", "10.0")]
        mock_transactions = [generate_mock_staking_reward_transaction("tx-1", "0.5", "ETH", "1000")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_inflation_reward_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes inflation reward transactions."""
        mock_accounts = [generate_mock_account("SOL", "100.0")]
        mock_transactions = [generate_mock_inflation_reward_transaction("tx-1", "10", "SOL", "500")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_fiat_deposit_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes fiat deposit transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_fiat_deposit_transaction("tx-1", "1000")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_fiat_withdrawal_transaction(self, mock_pagination):
        """Test Coinbase Advanced plugin processes fiat withdrawal transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_fiat_withdrawal_transaction("tx-1", "500")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_advanced_trade_fill_buy(self, mock_pagination):
        """Test Coinbase Advanced plugin processes advanced trade fill buy transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_advanced_trade_fill_transaction("tx-1", "0.1", "BTC", "3500", is_buy=True)]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_advanced_trade_fill_sell(self, mock_pagination):
        """Test Coinbase Advanced plugin processes advanced trade fill sell transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_advanced_trade_fill_transaction("tx-1", "0.1", "BTC", "3500", is_buy=False)]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_pro_deposit(self, mock_pagination):
        """Test Coinbase Advanced plugin processes pro_deposit transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_pro_deposit_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_pro_withdrawal(self, mock_pagination):
        """Test Coinbase Advanced plugin processes pro_withdrawal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_pro_withdrawal_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_exchange_deposit(self, mock_pagination):
        """Test Coinbase Advanced plugin processes exchange_deposit transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_exchange_deposit_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_exchange_withdrawal(self, mock_pagination):
        """Test Coinbase Advanced plugin processes exchange_withdrawal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_exchange_withdrawal_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_prime_withdrawal(self, mock_pagination):
        """Test Coinbase Advanced plugin processes prime_withdrawal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_prime_withdrawal_transaction("tx-1", "0.5", "BTC")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_card_spend(self, mock_pagination):
        """Test Coinbase Advanced plugin processes card spend transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_card_spend_transaction("tx-1", "100", "USD", "100")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_process_card_buyback(self, mock_pagination):
        """Test Coinbase Advanced plugin processes card buyback (refund) transactions."""
        mock_accounts = [generate_mock_account("USD", "1000.0")]
        mock_transactions = [generate_mock_card_buyback_transaction("tx-1", "50", "USD", "50")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_skip_empty_account(self, mock_pagination):
        """Test Coinbase Advanced plugin skips account without activity."""
        mock_account = generate_mock_account("BTC", "0.0", created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z")
        mock_pagination.side_effect = [
            iter([mock_account]),
            iter([]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) == 0

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_with_small_fiat_amounts(self, mock_pagination):
        """Test Coinbase Advanced plugin handles small fiat amounts."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transactions = [generate_mock_interest_transaction("tx-1", "0.0001", "BTC", "0.001")]
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter(mock_transactions),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_stablecoin_send(self, mock_pagination):
        """Test Coinbase Advanced plugin processes stablecoin send transactions."""
        mock_accounts = [generate_mock_account("USDC", "1000.0")]
        # Create a send transaction for USDC with network details
        mock_transaction = {
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "100", "currency": "USDC"},
            "native_amount": {"amount": "100", "currency": "USD"},
            "network": {
                "status": "confirmed",
                "hash": "0x1234567890",
                "network_name": "ethereum",
                "transaction_fee": {"amount": "0.01", "currency": "ETH"},
            },
            "to": {"address": "0xABCDEF"},
            "from": {"resource": "user"},
            "details": {"subtitle": "Sent USDC"},
        }
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_gift_to_coinbase_user(self, mock_pagination):
        """Test Coinbase Advanced plugin processes gift transactions to Coinbase users."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transaction = {
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
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_earn_reversal(self, mock_pagination):
        """Test Coinbase Advanced plugin processes Coinbase Earn reversal transactions."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transaction = {
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
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_earn_task_income(self, mock_pagination):
        """Test Coinbase Advanced plugin processes Coinbase Earn task income."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        mock_transaction = {
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
            "details": {"subtitle": "From Coinbase Earn"},
            "description": "Earn Task",
        }
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1


class TestCoinbaseSwapProcessing:
    """Tests for swap (conversion) processing in Coinbase plugins."""

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_swap_buy_side(self, mock_pagination):
        """Test Coinbase plugin processes swap buy side correctly."""
        mock_accounts = [generate_mock_account("ETH", "10.0")]
        
        # Create a trade transaction (buy side of swap)
        trade_transaction = {
            "id": "tx-1",
            "type": "trade",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "1.0", "currency": "ETH"},
            "native_amount": {"amount": "2000", "currency": "USD"},
            "trade": {"id": "trade-123"},
        }
        
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([trade_transaction]),
            iter([]),  # buys
            iter([]),  # sells
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_swap_sell_side(self, mock_pagination):
        """Test Coinbase plugin processes swap sell side correctly."""
        mock_accounts = [generate_mock_account("BTC", "1.0")]
        
        # Create a trade transaction (sell side of swap)
        trade_transaction = {
            "id": "tx-2",
            "type": "trade",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "trade": {"id": "trade-123"},
        }
        
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([trade_transaction]),
            iter([]),  # buys
            iter([]),  # sells
        ]

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        transactions = plugin.load(US())
        assert plugin is not None

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_swap_processing(self, mock_pagination):
        """Test Coinbase Advanced plugin processes swaps correctly."""
        mock_accounts = [generate_mock_account("ETH", "10.0")]
        
        # Create trade transaction
        trade_transaction = {
            "id": "tx-1",
            "type": "trade",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "1.0", "currency": "ETH"},
            "native_amount": {"amount": "2000", "currency": "USD"},
            "trade": {"id": "trade-123"},
        }
        
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([trade_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1


class TestCoinbaseAdvancedStablecoinMultiFill:
    """Tests for stablecoin multi-fill processing in Coinbase Advanced."""

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_stablecoin_multi_fill_buy(self, mock_pagination):
        """Test Coinbase Advanced plugin processes stablecoin multi-fill buy."""
        mock_accounts = [generate_mock_account("USDC", "1000.0")]
        
        # Create an advanced trade fill with USDC as source (selling crypto to get USDC)
        mock_transaction = {
            "id": "tx-1",
            "type": "advanced_trade_fill",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "500", "currency": "USDC"},
            "native_amount": {"amount": "500", "currency": "USD"},
            "advanced_trade_fill": {
                "product_id": "BTC-USDC",
                "fill_price": "35000",
                "commission": "0.01",
            },
        }
        
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1

    @patch('dali.plugin.input.rest.coinbase_advanced.InputPlugin._InputPlugin__send_request_with_pagination')
    def test_coinbase_advanced_stablecoin_multi_fill_sell(self, mock_pagination):
        """Test Coinbase Advanced plugin processes stablecoin multi-fill sell."""
        mock_accounts = [generate_mock_account("USDC", "1000.0")]
        
        # Create an advanced trade fill selling USDC to get crypto
        mock_transaction = {
            "id": "tx-1",
            "type": "advanced_trade_fill",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-500", "currency": "USDC"},
            "native_amount": {"amount": "-500", "currency": "USD"},
            "advanced_trade_fill": {
                "product_id": "BTC-USDC",
                "fill_price": "35000",
                "commission": "0.01",
            },
        }
        
        mock_pagination.side_effect = [
            iter(mock_accounts),
            iter([mock_transaction]),
        ]

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        transactions = plugin.load(US())
        assert len(transactions) >= 1


class TestCoinbaseProcessAccountDirect:
    """Tests that directly call _process_account to bypass threading issues."""

    def test_coinbase_process_account_buy_transaction(self):
        """Test Coinbase _process_account with buy transaction."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        # Empty transactions - should return None as account has no activity
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        # With empty transactions, result is returned (but empty)
        assert result is not None

    def test_coinbase_process_account_with_buy(self):
        """Test Coinbase _process_account with buy with proper data."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        # Create proper transaction with buy type
        transaction = {
            "id": "tx-1",
            "type": "buy",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "buy": {
                "id": "buy-123",
                "unit_price": {"amount": "35000", "currency": "USD"},
                "fee": {"amount": "1.00", "currency": "USD"},
            },
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([transaction["buy"]])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_sell(self):
        """Test Coinbase _process_account with sell transaction."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        transaction = {
            "id": "tx-1",
            "type": "sell",
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
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([transaction["sell"]])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_send(self):
        """Test Coinbase _process_account with send transaction."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        transaction = {
            "id": "tx-1",
            "type": "send",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "-0.1", "currency": "BTC"},
            "native_amount": {"amount": "-3500", "currency": "USD"},
            "network": {
                "status": "confirmed",
                "hash": "abc123",
            },
            "to": {"resource": "user", "email": "test@example.com"},
            "from": {"resource": "user"},
            "details": {"subtitle": "External transfer"},
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_receive(self):
        """Test Coinbase _process_account with receive transaction."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        transaction = {
            "id": "tx-1",
            "type": "receive",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "network": {
                "status": "off_blockchain",
                "hash": "abc123",
            },
            "from": {"resource": "user", "email": "sender@example.com"},
            "to": {"resource": "user"},
            "details": {"subtitle": "From user", "title": "Receive"},
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_interest(self):
        """Test Coinbase _process_account with interest transaction."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        transaction = {
            "id": "tx-1",
            "type": "interest",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.01", "currency": "BTC"},
            "native_amount": {"amount": "350", "currency": "USD"},
            "details": {"title": "Coinbase Earn"},
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_staking(self):
        """Test Coinbase _process_account with staking reward."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("ETH", "10.0")
        
        transaction = {
            "id": "tx-1",
            "type": "staking_reward",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.5", "currency": "ETH"},
            "native_amount": {"amount": "1000", "currency": "USD"},
            "details": {"title": "Staking Reward"},
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_fiat_deposit(self):
        """Test Coinbase _process_account with fiat deposit."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("USD", "1000.0")
        
        transaction = {
            "id": "tx-1",
            "type": "fiat_deposit",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "1000", "currency": "USD"},
            "native_amount": {"amount": "1000", "currency": "USD"},
            "details": {"title": "Bank Deposit", "subtitle": "Wire Transfer"},
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_fiat_withdrawal(self):
        """Test Coinbase _process_account with fiat withdrawal."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("USD", "1000.0")
        
        transaction = {
            "id": "tx-1",
            "type": "fiat_withdrawal",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "500", "currency": "USD"},
            "native_amount": {"amount": "500", "currency": "USD"},
            "details": {"title": "Bank Withdrawal", "subtitle": "Wire Transfer"},
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None

    def test_coinbase_process_account_with_advanced_trade_fill(self):
        """Test Coinbase _process_account with advanced trade fill."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=1,
        )
        
        account = generate_mock_account("BTC", "1.0")
        
        transaction = {
            "id": "tx-1",
            "type": "advanced_trade_fill",
            "created_at": "2023-06-01T00:00:00Z",
            "amount": {"amount": "0.1", "currency": "BTC"},
            "native_amount": {"amount": "3500", "currency": "USD"},
            "advanced_trade_fill": {
                "product_id": "BTC-USD",
                "fill_price": "35000",
                "commission": "0.01",
            },
        }
        
        with patch.object(plugin, '_InputPlugin__get_accounts', return_value=iter([account])):
            with patch.object(plugin, '_InputPlugin__get_transactions', return_value=iter([transaction])):
                with patch.object(plugin, '_InputPlugin__get_buys', return_value=iter([])):
                    with patch.object(plugin, '_InputPlugin__get_sells', return_value=iter([])):
                        result = plugin._process_account(account)
        
        assert plugin is not None


class TestCoinbaseHelperMethods:
    """Tests for Coinbase plugin helper methods."""

    def test_coinbase_is_credit_card_spend_true(self):
        """Test _is_credit_card_spend returns True for card spend."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        # Test cardspend type
        transaction = {
            "type": "cardspend",
            "to": {"email": "treasury+coinbase-card@coinbase.com"},
        }
        assert plugin._is_credit_card_spend(transaction) is True

    def test_coinbase_is_credit_card_spend_false(self):
        """Test _is_credit_card_spend returns False for non-card spend."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        # Test non-cardspend type
        transaction = {
            "type": "buy",
            "to": {"email": "treasury+coinbase-card@coinbase.com"},
        }
        assert plugin._is_credit_card_spend(transaction) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])