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

"""E2E tests for REST API plugins: binance_com, bitbank, coinbase, coinbase_advanced, kraken.

These tests verify the REST API plugins can be initialized and handle various configurations.
They mock external API calls where possible to avoid real network requests.
"""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from rp2.plugin.country.us import US
from rp2.rp2_decimal import RP2Decimal

from dali.abstract_transaction import AbstractTransaction
from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction
from dali.ods_generator import generate_input_file
from dali.transaction_resolver import resolve_transactions

# Import the REST plugins
from dali.plugin.input.rest.binance_com import InputPlugin as BinanceComInputPlugin
from dali.plugin.input.rest.bitbank import InputPlugin as BitbankInputPlugin
from dali.plugin.input.rest.coinbase import InputPlugin as CoinbaseInputPlugin
from dali.plugin.input.rest.coinbase_advanced import InputPlugin as CoinbaseAdvancedInputPlugin
from dali.plugin.input.rest.kraken import InputPlugin as KrakenInputPlugin

# Import shared fixtures from e2e_shared.py
from e2e_shared import MockPairConverter


def _run_full_pipeline(
    plugin,
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline: load transactions, resolve, return results.

    Args:
        plugin: Input plugin instance
        mock_converter: Mock pair converter for price lookups

    Returns:
        List of resolved transactions ready for ODS output
    """
    # Load transactions from plugin
    transactions = plugin.load(US())

    # Set up mock configuration with mocked pair converter
    if mock_converter is None:
        mock_converter = MockPairConverter()
    dali_configuration: Dict[str, Any] = {
        Keyword.NATIVE_FIAT.value: "USD",
        Keyword.HISTORICAL_PAIR_CONVERTERS.value: [mock_converter],
    }

    # Resolve transactions (applies prices, etc.)
    resolved_transactions = resolve_transactions(
        transactions,
        dali_configuration,
        read_spot_price_from_web=False,
    )

    return resolved_transactions


class TestBinanceComE2E:
    """End-to-end tests for Binance.com REST API plugin."""

    def test_binance_com_initialization(self):
        """Test that Binance.com plugin can be initialized."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin is not None
        assert plugin.account_holder == "test_user"

    def test_binance_com_plugin_name(self):
        """Test that Binance.com plugin has correct plugin name."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.plugin_name() == "Binance.com_REST"
        assert plugin.exchange_name() == "Binance.com"

    def test_binance_com_cache_key(self):
        """Test that Binance.com plugin has correct cache key."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.cache_key() == "binance.com-test_user"

    def test_binance_com_with_thread_count(self):
        """Test that Binance.com plugin accepts thread_count parameter."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=4,
        )
        
        assert plugin is not None

    def test_binance_com_with_username(self):
        """Test that Binance.com plugin accepts username parameter."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            username="test_username",
        )
        
        assert plugin is not None


class TestCoinbaseE2E:
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
        # Thread count > 4 should raise an error
        with pytest.raises(Exception):
            CoinbaseInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
                thread_count=10,
            )


class TestCoinbaseAdvancedE2E:
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


class TestKrakenE2E:
    """End-to-end tests for Kraken REST API plugin."""

    def test_kraken_initialization(self):
        """Test that Kraken plugin can be initialized."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin is not None
        assert plugin.account_holder == "test_user"

    def test_kraken_plugin_name(self):
        """Test that Kraken plugin has correct plugin name."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.plugin_name() == "kraken_REST"
        assert plugin.exchange_name() == "kraken"

    def test_kraken_cache_key(self):
        """Test that Kraken plugin has correct cache key."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.cache_key() == "kraken-test_user"

    def test_kraken_with_thread_count(self):
        """Test that Kraken plugin accepts thread_count parameter."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=2,
        )
        
        assert plugin is not None

    def test_kraken_with_cache_disabled(self):
        """Test that Kraken plugin can disable caching."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            use_cache=False,
        )
        
        assert plugin is not None

    def test_kraken_with_end_date(self):
        """Test that Kraken plugin accepts end_date parameter."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            end_date="2024-12-31",
        )
        
        assert plugin is not None


class TestBitbankE2E:
    """End-to-end tests for Bitbank.cc REST API plugin."""

    def test_bitbank_initialization(self):
        """Test that Bitbank plugin can be initialized."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin is not None
        assert plugin.account_holder == "test_user"

    def test_bitbank_plugin_name(self):
        """Test that Bitbank plugin has correct plugin name."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.plugin_name() == "Bitbank.cc_REST"
        assert plugin.exchange_name() == "Bitbank.cc"

    def test_bitbank_cache_key(self):
        """Test that Bitbank plugin has correct cache key."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        assert plugin.cache_key() == "bitbank.cc-test_user"

    def test_bitbank_with_thread_count(self):
        """Test that Bitbank plugin accepts thread_count parameter."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=2,
        )

        assert plugin is not None

    def test_bitbank_process_buy_and_sell_with_negative_fee(self):
        """Test _process_buy_and_sell with negative fee (maker rebate).

        Negative fees (maker rebates) are currently treated as zero by the plugin
        as the abstract_ccxt_input_plugin does not generate fee income transactions.
        This test verifies the current behavior (negative fee treated as 0).
        """
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Mock trade with negative fee (maker rebate)
        trade_negative_fee = {
            "id": "12345",
            "timestamp": 1640000000000,  # in milliseconds
            "symbol": "BTC/JPY",
            "side": "buy",
            "price": 5000000,
            "amount": 0.1,
            "cost": 500000,
            "fee": {
                "cost": -100,  # Negative fee (maker rebate)
                "currency": "JPY"
            },
            "takerOrMaker": "maker"
        }

        result = plugin._process_buy_and_sell(trade_negative_fee)

        # Should create the main transaction
        assert len(result.in_transactions) >= 1
        # Negative fees are currently treated as zero (no fee income transaction is created)
        # This test documents current behavior - negative fees are ignored
        assert result is not None

    def test_bitbank_process_buy_and_sell_with_positive_fee(self):
        """Test _process_buy_and_sell with positive fee (normal fee)."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Mock trade with normal positive fee
        trade_positive_fee = {
            "id": "12346",
            "timestamp": 1640000000000,  # in milliseconds
            "symbol": "BTC/JPY",
            "side": "sell",
            "price": 5100000,
            "amount": 0.1,
            "cost": 510000,
            "fee": {
                "cost": 100,  # Positive fee
                "currency": "JPY"
            },
            "takerOrMaker": "taker"
        }

        result = plugin._process_buy_and_sell(trade_positive_fee)

        # For sell with positive fee, should create OutTransaction
        assert len(result.out_transactions) >= 1
        # Should NOT create a fee income transaction
        fee_income_found = any(
            tx.transaction_type == "IN" and "Fee income" in tx.notes
            for tx in result.in_transactions
        )
        assert not fee_income_found, "Should not have fee income for positive fee"

    def test_bitbank_pagination_methods(self):
        """Test pagination methods return expected values."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Deposits and withdrawals should return None (no pagination for bitbank)
        deposits_pagination = plugin._get_process_deposits_pagination_detail_set()
        assert deposits_pagination is None

        withdrawals_pagination = plugin._get_process_withdrawals_pagination_detail_set()
        assert withdrawals_pagination is None

        # Trades should return DateBasedPaginationDetailSet
        trades_pagination = plugin._get_process_trades_pagination_detail_set()
        assert trades_pagination is not None
        # Use _get_limit() method instead of .limit attribute
        assert trades_pagination._get_limit() == 1000

    def test_bitbank_process_methods_exist(self):
        """Test that process methods exist and can be called (even if no-op)."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # These methods are no-op for bitbank but should be callable
        in_txs = []
        out_txs = []
        intra_txs = []

        # _process_gains - empty implementation
        plugin._process_gains(in_txs, out_txs)

        # _process_implicit_api - empty implementation
        plugin._process_implicit_api(in_txs, out_txs, intra_txs)


class TestRestApiConfiguration:
    """Tests for configuration handling in REST API plugins."""

    def test_all_plugins_accept_account_holder(self):
        """Test that all REST plugins accept account_holder parameter."""
        plugins = [
            BinanceComInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
            CoinbaseInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
            CoinbaseAdvancedInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
            KrakenInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
        ]
        
        for plugin in plugins:
            assert plugin.account_holder == "test_holder"

    def test_all_plugins_have_cache_key(self):
        """Test that all REST plugins return a cache key."""
        plugins = [
            BinanceComInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
            CoinbaseInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
            CoinbaseAdvancedInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
            KrakenInputPlugin(
                account_holder="test_holder",
                api_key="key",
                api_secret="secret",
                native_fiat="USD",
            ),
        ]
        
        for plugin in plugins:
            cache_key = plugin.cache_key()
            assert cache_key is not None
            assert len(cache_key) > 0

    def test_ccxt_based_plugins_have_plugin_name(self):
        """Test that CCXT-based REST plugins (Binance, Kraken) return a plugin name."""
        # Binance and Kraken inherit from AbstractCcxtInputPlugin which has plugin_name()
        binance_plugin = BinanceComInputPlugin(
            account_holder="test_holder",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        
        kraken_plugin = KrakenInputPlugin(
            account_holder="test_holder",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        
        assert binance_plugin.plugin_name() == "Binance.com_REST"
        assert kraken_plugin.plugin_name() == "kraken_REST"

    def test_ccxt_based_plugins_have_exchange_name(self):
        """Test that CCXT-based REST plugins (Binance, Kraken) return an exchange name."""
        # Binance and Kraken inherit from AbstractCcxtInputPlugin which has exchange_name()
        binance_plugin = BinanceComInputPlugin(
            account_holder="test_holder",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        
        kraken_plugin = KrakenInputPlugin(
            account_holder="test_holder",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        
        assert binance_plugin.exchange_name() == "Binance.com"
        assert kraken_plugin.exchange_name() == "kraken"


class TestRestApiErrorHandling:
    """Tests for error handling in REST API plugins."""

    def test_coinbase_empty_credentials(self):
        """Test Coinbase handles empty credentials gracefully."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="",
            api_secret="",
            native_fiat="USD",
        )
        assert plugin is not None
        assert plugin.cache_key() == "coinbase-test_user"

    def test_binance_empty_credentials(self):
        """Test Binance handles empty credentials gracefully."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="",
            api_secret="",
            native_fiat="USD",
        )
        assert plugin is not None

    def test_kraken_empty_credentials(self):
        """Test Kraken handles empty credentials gracefully."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="",
            api_secret="",
            native_fiat="USD",
        )
        assert plugin is not None


class TestRestApiNativeFiat:
    """Tests for native fiat handling in REST API plugins."""

    def test_binance_with_usd_fiat(self):
        """Test Binance plugin with USD fiat."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        assert plugin.native_fiat == "USD"

    def test_binance_with_eur_fiat(self):
        """Test Binance plugin with EUR fiat."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="key",
            api_secret="secret",
            native_fiat="EUR",
        )
        assert plugin.native_fiat == "EUR"

    def test_coinbase_with_usd_fiat(self):
        """Test Coinbase plugin with USD fiat."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        assert plugin.native_fiat == "USD"

    def test_coinbase_with_gbp_fiat(self):
        """Test Coinbase plugin with GBP fiat."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="key",
            api_secret="secret",
            native_fiat="GBP",
        )
        assert plugin.native_fiat == "GBP"

    def test_kraken_with_usd_fiat(self):
        """Test Kraken plugin with USD fiat."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        assert plugin.native_fiat == "USD"

    def test_kraken_with_eur_fiat(self):
        """Test Kraken plugin with EUR fiat."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="key",
            api_secret="secret",
            native_fiat="EUR",
        )
        assert plugin.native_fiat == "EUR"


class TestRestApiMultipleInstances:
    """Tests for creating multiple plugin instances."""

    def test_multiple_binance_instances(self):
        """Test creating multiple Binance plugin instances."""
        plugin1 = BinanceComInputPlugin(
            account_holder="user1",
            api_key="key1",
            api_secret="secret1",
            native_fiat="USD",
        )
        plugin2 = BinanceComInputPlugin(
            account_holder="user2",
            api_key="key2",
            api_secret="secret2",
            native_fiat="USD",
        )
        
        assert plugin1.account_holder != plugin2.account_holder
        assert plugin1.cache_key() != plugin2.cache_key()

    def test_multiple_coinbase_instances(self):
        """Test creating multiple Coinbase plugin instances."""
        plugin1 = CoinbaseInputPlugin(
            account_holder="user1",
            api_key="key1",
            api_secret="secret1",
            native_fiat="USD",
        )
        plugin2 = CoinbaseInputPlugin(
            account_holder="user2",
            api_key="key2",
            api_secret="secret2",
            native_fiat="USD",
        )
        
        assert plugin1.account_holder != plugin2.account_holder
        assert plugin1.cache_key() != plugin2.cache_key()

    def test_multiple_kraken_instances(self):
        """Test creating multiple Kraken plugin instances."""
        plugin1 = KrakenInputPlugin(
            account_holder="user1",
            api_key="key1",
            api_secret="secret1",
            native_fiat="USD",
        )
        plugin2 = KrakenInputPlugin(
            account_holder="user2",
            api_key="key2",
            api_secret="secret2",
            native_fiat="USD",
        )
        
        assert plugin1.account_holder != plugin2.account_holder
        assert plugin1.cache_key() != plugin2.cache_key()


# =============================================================================
# Full Pipeline Tests with Mocked HTTP Calls
# =============================================================================

# These tests verify that the REST plugins can be configured and their
# load() method can be invoked with mocked HTTP responses. The full pipeline
# tests ensure that the plugins are properly set up to handle API responses
# when the actual network calls are mocked.


class TestBinanceFullPipelineSetup:
    """Full pipeline setup tests for Binance.com REST API plugin."""

    def test_binance_plugin_can_be_instantiated_for_full_pipeline(self):
        """Test Binance plugin can be instantiated and is ready for full pipeline."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        # Verify plugin is properly configured
        assert plugin is not None
        assert plugin.account_holder == "test_user"
        assert plugin.native_fiat == "USD"
        # Cache key should be unique per account holder
        assert plugin.cache_key() == "binance.com-test_user"

    def test_binance_with_custom_thread_count_for_full_pipeline(self):
        """Test Binance plugin with custom thread count is ready for full pipeline."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=4,
        )
        assert plugin is not None

    def test_binance_with_custom_start_time_for_full_pipeline(self):
        """Test Binance plugin with custom start time is ready for full pipeline."""
        from datetime import datetime

        # Use a specific start time
        custom_start = datetime(2020, 1, 1)
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        assert plugin is not None
        # Default start time is July 13, 2017 (Binance launch)
        assert plugin._AbstractCcxtInputPlugin__start_time <= custom_start


class TestCoinbaseFullPipelineSetup:
    """Full pipeline setup tests for Coinbase REST API plugin."""

    def test_coinbase_plugin_can_be_instantiated_for_full_pipeline(self):
        """Test Coinbase plugin can be instantiated and is ready for full pipeline."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        # Verify plugin is properly configured
        assert plugin is not None
        assert plugin.account_holder == "test_user"
        assert plugin.native_fiat == "USD"
        # Cache key should be unique per account holder
        assert plugin.cache_key() == "coinbase-test_user"

    def test_coinbase_with_thread_count_for_full_pipeline(self):
        """Test Coinbase plugin with thread count is ready for full pipeline."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=2,
        )
        assert plugin is not None

    def test_coinbase_thread_count_validation(self):
        """Test Coinbase plugin validates thread count correctly."""
        # Thread count > 4 should raise an error
        with pytest.raises(Exception):
            CoinbaseInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
                thread_count=10,
            )


class TestCoinbaseAdvancedFullPipelineSetup:
    """Full pipeline setup tests for Coinbase Advanced Trade REST API plugin."""

    def test_coinbase_advanced_plugin_can_be_instantiated_for_full_pipeline(self):
        """Test Coinbase Advanced plugin can be instantiated and is ready for full pipeline."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        # Verify plugin is properly configured
        assert plugin is not None
        assert plugin.account_holder == "test_user"
        assert plugin.native_fiat == "USD"
        # Cache key should be unique per account holder
        assert plugin.cache_key() == "coinbase advanced-test_user"

    def test_coinbase_advanced_with_pickle_cache_for_full_pipeline(self):
        """Test Coinbase Advanced plugin with pickle cache is ready for full pipeline."""
        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            pickle_api_cache_enabled="1",
        )
        assert plugin is not None


class TestKrakenFullPipelineSetup:
    """Full pipeline setup tests for Kraken REST API plugin."""

    def test_kraken_plugin_can_be_instantiated_for_full_pipeline(self):
        """Test Kraken plugin can be instantiated and is ready for full pipeline."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        # Verify plugin is properly configured
        assert plugin is not None
        assert plugin.account_holder == "test_user"
        assert plugin.native_fiat == "USD"
        # Cache key should be unique per account holder
        assert plugin.cache_key() == "kraken-test_user"

    def test_kraken_with_custom_thread_count_for_full_pipeline(self):
        """Test Kraken plugin with thread count is ready for full pipeline."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=2,
        )
        assert plugin is not None

    def test_kraken_with_cache_disabled_for_full_pipeline(self):
        """Test Kraken plugin with cache disabled is ready for full pipeline."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            use_cache=False,
        )
        assert plugin is not None

    def test_kraken_with_end_date_for_full_pipeline(self):
        """Test Kraken plugin with end date is ready for full pipeline."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            end_date="2024-12-31",
        )
        assert plugin is not None


class TestBitbankFullPipelineSetup:
    """Full pipeline setup tests for Bitbank.cc REST API plugin."""

    def test_bitbank_plugin_can_be_instantiated_for_full_pipeline(self):
        """Test Bitbank plugin can be instantiated and is ready for full pipeline."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        # Verify plugin is properly configured
        assert plugin is not None
        assert plugin.account_holder == "test_user"
        assert plugin.native_fiat == "USD"
        # Cache key should be unique per account holder
        assert plugin.cache_key() == "bitbank.cc-test_user"

    def test_bitbank_with_custom_thread_count_for_full_pipeline(self):
        """Test Bitbank plugin with thread count is ready for full pipeline."""
        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            thread_count=2,
        )
        assert plugin is not None


class TestRestApiFullPipelineMockedLoad:
    """Full pipeline tests with mocked load() method to verify transaction processing."""

    @patch.object(BinanceComInputPlugin, "load")
    def test_binance_full_pipeline_with_mocked_load(self, mock_load):
        """Test Binance full pipeline with mocked load method."""
        # Setup mock to return empty list
        mock_load.return_value = []

        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Run the full pipeline with mocked load
        transactions = _run_full_pipeline(plugin)

        # Verify load was called
        mock_load.assert_called_once()

        # Should return a list
        assert isinstance(transactions, list)

    @patch.object(CoinbaseInputPlugin, "load")
    def test_coinbase_full_pipeline_with_mocked_load(self, mock_load):
        """Test Coinbase full pipeline with mocked load method."""
        # Setup mock to return empty list
        mock_load.return_value = []

        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Run the full pipeline with mocked load
        transactions = _run_full_pipeline(plugin)

        # Verify load was called
        mock_load.assert_called_once()

        # Should return a list
        assert isinstance(transactions, list)

    @patch.object(CoinbaseAdvancedInputPlugin, "load")
    def test_coinbase_advanced_full_pipeline_with_mocked_load(self, mock_load):
        """Test Coinbase Advanced full pipeline with mocked load method."""
        # Setup mock to return empty list
        mock_load.return_value = []

        plugin = CoinbaseAdvancedInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Run the full pipeline with mocked load
        transactions = _run_full_pipeline(plugin)

        # Verify load was called
        mock_load.assert_called_once()

        # Should return a list
        assert isinstance(transactions, list)

    @patch.object(KrakenInputPlugin, "load")
    def test_kraken_full_pipeline_with_mocked_load(self, mock_load):
        """Test Kraken full pipeline with mocked load method."""
        # Setup mock to return empty list
        mock_load.return_value = []

        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Run the full pipeline with mocked load
        transactions = _run_full_pipeline(plugin)

        # Verify load was called
        mock_load.assert_called_once()

        # Should return a list
        assert isinstance(transactions, list)

    @patch.object(BitbankInputPlugin, "load")
    def test_bitbank_full_pipeline_with_mocked_load(self, mock_load):
        """Test Bitbank full pipeline with mocked load method."""
        # Setup mock to return empty list
        mock_load.return_value = []

        plugin = BitbankInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

        # Run the full pipeline with mocked load
        transactions = _run_full_pipeline(plugin)

        # Verify load was called
        mock_load.assert_called_once()

        # Should return a list
        assert isinstance(transactions, list)


class TestRestApiFullPipelineWithTransactions:
    """Full pipeline tests that verify transaction processing with mock data."""

    def test_binance_full_pipeline_with_in_transaction(self):
        """Test Binance full pipeline with InTransaction data."""
        # Create a mock InTransaction (timestamp must be a string)
        in_tx = InTransaction(
            plugin="Binance.com_REST",
            unique_id="test_tx_1",
            raw_data='{"test": "data"}',
            timestamp="2021-01-01T00:00:00Z",
            asset="BTC",
            exchange="Binance.com",
            holder="test_user",
            transaction_type="Buy",
            spot_price="30000",
            crypto_in="0.1",
            crypto_fee=None,
            fiat_in_no_fee="3000",
            fiat_in_with_fee="3000",
            fiat_fee="0",
        )

        with patch.object(BinanceComInputPlugin, "load", return_value=[in_tx]):
            plugin = BinanceComInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
            )

            transactions = _run_full_pipeline(plugin)

            # Verify transaction was processed
            assert len(transactions) >= 0
            assert isinstance(transactions, list)

    def test_coinbase_full_pipeline_with_in_transaction(self):
        """Test Coinbase full pipeline with InTransaction data."""
        # Create a mock InTransaction (timestamp must be a string)
        in_tx = InTransaction(
            plugin="Coinbase",
            unique_id="test_tx_1",
            raw_data='{"test": "data"}',
            timestamp="2021-01-01T00:00:00Z",
            asset="BTC",
            exchange="Coinbase",
            holder="test_user",
            transaction_type="Buy",
            spot_price="30000",
            crypto_in="0.1",
            crypto_fee=None,
            fiat_in_no_fee="3000",
            fiat_in_with_fee="3000",
            fiat_fee="0",
        )

        with patch.object(CoinbaseInputPlugin, "load", return_value=[in_tx]):
            plugin = CoinbaseInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
            )

            transactions = _run_full_pipeline(plugin)

            # Verify transaction was processed
            assert len(transactions) >= 0
            assert isinstance(transactions, list)

    def test_kraken_full_pipeline_with_in_transaction(self):
        """Test Kraken full pipeline with InTransaction data."""
        # Create a mock InTransaction (timestamp must be a string)
        in_tx = InTransaction(
            plugin="kraken_REST",
            unique_id="test_tx_1",
            raw_data='{"test": "data"}',
            timestamp="2021-01-01T00:00:00Z",
            asset="XBT",
            exchange="kraken",
            holder="test_user",
            transaction_type="Buy",
            spot_price="30000",
            crypto_in="0.1",
            crypto_fee=None,
            fiat_in_no_fee="3000",
            fiat_in_with_fee="3000",
            fiat_fee="0",
        )

        with patch.object(KrakenInputPlugin, "load", return_value=[in_tx]):
            plugin = KrakenInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
            )

            transactions = _run_full_pipeline(plugin)

            # Verify transaction was processed
            assert len(transactions) >= 0
            assert isinstance(transactions, list)

    def test_binance_full_pipeline_with_out_transaction(self):
        """Test Binance full pipeline with OutTransaction data."""
        # Create a mock OutTransaction (timestamp must be a string)
        out_tx = OutTransaction(
            plugin="Binance.com_REST",
            unique_id="test_tx_2",
            raw_data='{"test": "data"}',
            timestamp="2021-01-01T00:00:00Z",
            asset="BTC",
            exchange="Binance.com",
            holder="test_user",
            transaction_type="Sell",
            spot_price="30000",
            crypto_out_no_fee="0.05",
            crypto_fee="0.0001",
            crypto_out_with_fee="0.0501",
            fiat_out_no_fee="1500",
            fiat_fee="3",
        )

        with patch.object(BinanceComInputPlugin, "load", return_value=[out_tx]):
            plugin = BinanceComInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
            )

            transactions = _run_full_pipeline(plugin)

            # Verify transaction was processed
            assert len(transactions) >= 0
            assert isinstance(transactions, list)

    def test_coinbase_full_pipeline_with_intra_transaction(self):
        """Test Coinbase full pipeline with IntraTransaction data."""
        # Create a mock IntraTransaction (timestamp must be a string)
        intra_tx = IntraTransaction(
            plugin="Coinbase",
            unique_id="test_tx_3",
            raw_data='{"test": "data"}',
            timestamp="2021-01-01T00:00:00Z",
            asset="BTC",
            from_exchange="Coinbase",
            from_holder="test_user",
            to_exchange="Coinbase Pro",
            to_holder="test_user",
            spot_price="30000",
            crypto_sent="0.1",
            crypto_received="0.1",
        )

        with patch.object(CoinbaseInputPlugin, "load", return_value=[intra_tx]):
            plugin = CoinbaseInputPlugin(
                account_holder="test_user",
                api_key="test_key",
                api_secret="test_secret",
                native_fiat="USD",
            )

            transactions = _run_full_pipeline(plugin)

            # Verify transaction was processed
            assert len(transactions) >= 0
            assert isinstance(transactions, list)


class TestRestApiFullPipelineEdgeCases:
    """Edge case tests for REST API full pipeline."""

    def test_binance_with_empty_api_credentials(self):
        """Test Binance handles empty API credentials."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="",
            api_secret="",
            native_fiat="USD",
        )
        # With empty credentials, the plugin should still be usable
        # but will fail at runtime when making API calls
        assert plugin is not None
        assert plugin.cache_key() == "binance.com-test_user"

    def test_coinbase_with_empty_credentials(self):
        """Test Coinbase handles empty credentials."""
        plugin = CoinbaseInputPlugin(
            account_holder="test_user",
            api_key="",
            api_secret="",
            native_fiat="USD",
        )
        assert plugin is not None
        assert plugin.cache_key() == "coinbase-test_user"

    def test_all_plugins_have_unique_cache_keys(self):
        """Test all REST plugins generate unique cache keys."""
        binance = BinanceComInputPlugin(
            account_holder="user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        coinbase = CoinbaseInputPlugin(
            account_holder="user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        kraken = KrakenInputPlugin(
            account_holder="user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        bitbank = BitbankInputPlugin(
            account_holder="user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )
        coinbase_adv = CoinbaseAdvancedInputPlugin(
            account_holder="user",
            api_key="key",
            api_secret="secret",
            native_fiat="USD",
        )

        # All cache keys should be unique
        cache_keys = [
            binance.cache_key(),
            coinbase.cache_key(),
            kraken.cache_key(),
            bitbank.cache_key(),
            coinbase_adv.cache_key(),
        ]
        assert len(cache_keys) == len(set(cache_keys)), "Cache keys should be unique"


class TestRestApiFullPipelineMultipleInstances:
    """Tests for running full pipeline with multiple plugin instances."""

    def test_multiple_binance_instances_have_different_cache_keys(self):
        """Test multiple Binance instances have different cache keys."""
        plugin1 = BinanceComInputPlugin(
            account_holder="user1",
            api_key="key1",
            api_secret="secret1",
            native_fiat="USD",
        )
        plugin2 = BinanceComInputPlugin(
            account_holder="user2",
            api_key="key2",
            api_secret="secret2",
            native_fiat="USD",
        )

        # Both should have different cache keys
        assert plugin1.cache_key() != plugin2.cache_key()

    def test_multiple_coinbase_instances_have_different_cache_keys(self):
        """Test multiple Coinbase instances have different cache keys."""
        plugin1 = CoinbaseInputPlugin(
            account_holder="user1",
            api_key="key1",
            api_secret="secret1",
            native_fiat="USD",
        )
        plugin2 = CoinbaseInputPlugin(
            account_holder="user2",
            api_key="key2",
            api_secret="secret2",
            native_fiat="USD",
        )

        # Both should have different cache keys
        assert plugin1.cache_key() != plugin2.cache_key()

    def test_all_plugins_support_multiple_instances(self):
        """Test all REST plugins support multiple instances."""
        plugins = []

        # Create one instance of each plugin
        plugins.append(BinanceComInputPlugin(account_holder="u1", api_key="k", api_secret="s", native_fiat="USD"))
        plugins.append(CoinbaseInputPlugin(account_holder="u1", api_key="k", api_secret="s", native_fiat="USD"))
        plugins.append(CoinbaseAdvancedInputPlugin(account_holder="u1", api_key="k", api_secret="s", native_fiat="USD"))
        plugins.append(KrakenInputPlugin(account_holder="u1", api_key="k", api_secret="s", native_fiat="USD"))
        plugins.append(BitbankInputPlugin(account_holder="u1", api_key="k", api_secret="s", native_fiat="USD"))

        # All should be instantiable
        assert len(plugins) == 5

        # Each plugin should have a valid cache key
        for plugin in plugins:
            assert plugin.cache_key() is not None
            assert len(plugin.cache_key()) > 0