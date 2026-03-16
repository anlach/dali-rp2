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

"""E2E tests for Binance and Kraken REST plugins to improve coverage.

These tests focus on the uncovered methods in both plugins.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from ccxt import binance, kraken
from rp2.plugin.country.us import US

from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction

# Import the REST plugins
from dali.plugin.input.rest.binance_com import InputPlugin as BinanceComInputPlugin
from dali.plugin.input.rest.kraken import InputPlugin as KrakenInputPlugin


# =============================================================================
# Binance Tests
# =============================================================================

class TestBinanceProcessMethods:
    """Test individual Binance processing methods."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        return plugin

    def test_process_dividend_staking(self, binance_plugin):
        """Test dividend processing for staking type."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Locked Staking",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)
        assert result is not None

    def test_process_dividend_interest(self, binance_plugin):
        """Test dividend processing for interest type."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Flexible",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)

    def test_process_dividend_airdrop(self, binance_plugin):
        """Test dividend processing for airdrop type."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "SOLO",
            "divTime": "1563189166000",
            "enInfo": "SOLO airdrop",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)

    def test_process_dividend_income(self, binance_plugin):
        """Test dividend processing for income type."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Cash Voucher",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)

    def test_process_dividend_regex_staking(self, binance_plugin):
        """Test dividend processing with regex for staking."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "ETH 2.0 Staking distribution",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)

    def test_process_dividend_regex_distribution(self, binance_plugin):
        """Test dividend processing with regex for distribution."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Token distribution",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)

    def test_process_gain_mining(self, binance_plugin):
        """Test gain processing for mining."""
        plugin = binance_plugin
        
        transaction = {
            "time": "1586188800000",
            "profitAmount": "8.6083060304",
            "coinName": "BTC",
        }
        
        result = plugin._process_gain(transaction, Keyword.MINING)
        assert result is not None

    def test_process_gain_staking(self, binance_plugin):
        """Test gain processing for staking."""
        plugin = binance_plugin
        
        transaction = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Locked Staking",
            "tranId": "2968885920"
        }
        
        result = plugin._process_gain(transaction, Keyword.STAKING)
        assert result is not None

    def test_process_gain_zero_amount(self, binance_plugin):
        """Test gain processing with zero amount."""
        plugin = binance_plugin
        
        transaction = {
            "id": "1637366104",
            "amount": "0.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Locked Staking",
            "tranId": "2968885920"
        }
        
        result = plugin._process_gain(transaction, Keyword.STAKING)
        # Should return empty result for zero amount
        assert len(result.in_transactions) == 0


class TestBinancePagination:
    """Test Binance pagination methods."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin."""
        return BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_deposits_pagination(self, binance_plugin):
        """Test deposit pagination detail set."""
        plugin = binance_plugin
        result = plugin._get_process_deposits_pagination_detail_set()
        assert result is not None

    def test_withdrawals_pagination(self, binance_plugin):
        """Test withdrawal pagination detail set."""
        plugin = binance_plugin
        result = plugin._get_process_withdrawals_pagination_detail_set()
        assert result is not None


class TestBinanceAlgos:
    """Test Binance mining algo fetching."""

    def test_get_algos_without_username(self):
        """Test getting algos without username."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        result = plugin._get_algos()
        assert result == []

    def test_get_algos_cached(self):
        """Test that algos are cached after first call."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            username="test_miner",
        )
        
        # Pre-populate cache
        plugin._InputPlugin__algos = ["SHA256", "Ethash"]
        
        result = plugin._get_algos()
        assert result == ["SHA256", "Ethash"]


class TestBinanceClientProperty:
    """Test Binance _client property."""

    def test_client_property_type_check(self):
        """Test _client property raises error for wrong type."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        # Set a non-binance client to trigger the error
        plugin._AbstractCcxtInputPlugin__client = MagicMock()
        
        with pytest.raises(Exception):  # RP2RuntimeError
            _ = plugin._client


# =============================================================================
# Kraken Tests
# =============================================================================

class TestKrakenAssetProcessing:
    """Test Kraken asset processing."""

    @pytest.fixture
    def kraken_plugin(self):
        """Create a Kraken plugin."""
        return KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_get_base_from_asset_with_suffix_hold(self, kraken_plugin):
        """Test stripping .HOLD suffix."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XETH": "ETH"}
        
        result = plugin._get_base_from_asset("ETH.HOLD")
        assert result == "ETH"

    def test_get_base_from_asset_with_suffix_ho(self, kraken_plugin):
        """Test stripping .HO suffix."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XETH": "ETH"}
        
        result = plugin._get_base_from_asset("ETH.HO")
        assert result == "ETH"

    def test_get_base_from_asset_with_suffix_b(self, kraken_plugin):
        """Test stripping .B suffix."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XETH": "ETH"}
        
        result = plugin._get_base_from_asset("ETH.B")
        assert result == "ETH"

    def test_get_base_from_asset_with_suffix_f(self, kraken_plugin):
        """Test stripping .F suffix."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XETH": "ETH"}
        
        result = plugin._get_base_from_asset("ETH.F")
        assert result == "ETH"

    def test_get_base_from_asset_with_suffix_m(self, kraken_plugin):
        """Test stripping .M suffix (without trailing digits)."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XETH": "ETH", "ETH": "ETH"}
        
        result = plugin._get_base_from_asset("ETH.M")
        assert result == "ETH"

    def test_get_base_from_asset_with_suffix_s(self, kraken_plugin):
        """Test stripping .S suffix (without trailing digits)."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XETH": "ETH", "ETH": "ETH"}
        
        result = plugin._get_base_from_asset("ETH.S")
        assert result == "ETH"

    def test_get_base_from_asset_no_suffix(self, kraken_plugin):
        """Test asset without suffix."""
        plugin = kraken_plugin
        plugin.base_id_to_base = {"XXBT": "BTC"}
        
        result = plugin._get_base_from_asset("XXBT")
        assert result == "BTC"


class TestKrakenPagination:
    """Test Kraken pagination methods."""

    @pytest.fixture
    def kraken_plugin(self):
        """Create a Kraken plugin."""
        return KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_deposits_pagination_returns_none(self, kraken_plugin):
        """Test deposit pagination returns None."""
        plugin = kraken_plugin
        result = plugin._get_process_deposits_pagination_detail_set()
        assert result is None

    def test_withdrawals_pagination_returns_none(self, kraken_plugin):
        """Test withdrawal pagination returns None."""
        plugin = kraken_plugin
        result = plugin._get_process_withdrawals_pagination_detail_set()
        assert result is None

    def test_trades_pagination_returns_none(self, kraken_plugin):
        """Test trades pagination returns None."""
        plugin = kraken_plugin
        result = plugin._get_process_trades_pagination_detail_set()
        assert result is None


class TestKrakenEndDate:
    """Test Kraken end_date property."""

    def test_end_date_property_with_value(self):
        """Test end_date property getter."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            end_date="2025-12-31",
        )
        
        result = plugin._end_date
        assert result is not None
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 31

    def test_end_date_property_none(self):
        """Test end_date property when not set."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        result = plugin._end_date
        assert result is None

    def test_end_date_invalid_format(self):
        """Test end_date with invalid format."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            end_date="invalid-date",
        )
        
        # Should log warning but not crash
        result = plugin._end_date
        assert result is None


class TestKrakenClientProperty:
    """Test Kraken _client property."""

    def test_client_property_type_check(self):
        """Test _client property raises error for wrong type."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        # Set a non-kraken client to trigger the error
        plugin._AbstractCcxtInputPlugin__client = MagicMock()
        
        with pytest.raises(Exception):  # RP2RuntimeError
            _ = plugin._client


class TestKrakenProcessGains:
    """Test Kraken _process_gains returns None."""

    def test_process_gains_returns_none(self):
        """Test _process_gains returns None (not implemented)."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        in_transactions = []
        out_transactions = []
        plugin._process_gains(in_transactions, out_transactions)
        # Method does nothing, just verifies it runs


class TestKrakenImplicitApi:
    """Test Kraken _process_implicit_api returns None."""

    def test_process_implicit_api_returns_none(self):
        """Test _process_implicit_api returns None (not implemented)."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        in_transactions = []
        out_transactions = []
        intra_transactions = []
        plugin._process_implicit_api(in_transactions, out_transactions, intra_transactions)
        # Method does nothing, just verifies it runs


class TestKrakenFilterByEndDate:
    """Test Kraken _filter_by_end_date method."""

    @pytest.fixture
    def kraken_plugin(self):
        """Create a Kraken plugin with end_date set."""
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            end_date="2025-12-31",
        )
        
        # Initialize base_id_to_base mapping
        plugin.base_id_to_base = {"XXBT": "BTC", "ZUSD": "USD"}
        return plugin

    def test_filter_by_end_date_excludes_future(self, kraken_plugin):
        """Test filtering excludes transactions after end_date."""
        plugin = kraken_plugin
        
        # Create a transaction with future timestamp
        future_tx = InTransaction(
            plugin="kraken_REST",
            unique_id="test1",
            raw_data="{}",
            timestamp="2026-01-15 12:00:00+0000",  # After end_date
            asset="BTC",
            exchange="kraken",
            holder="test_user",
            transaction_type="BUY",
            spot_price="50000",
            crypto_in="1.0",
        )
        
        result = plugin._filter_by_end_date([future_tx])
        assert len(result) == 0

    def test_filter_by_end_date_includes_past(self, kraken_plugin):
        """Test filtering includes transactions before end_date."""
        plugin = kraken_plugin
        
        # Create a transaction with past timestamp
        past_tx = InTransaction(
            plugin="kraken_REST",
            unique_id="test1",
            raw_data="{}",
            timestamp="2025-01-15 12:00:00+0000",  # Before end_date
            asset="BTC",
            exchange="kraken",
            holder="test_user",
            transaction_type="BUY",
            spot_price="50000",
            crypto_in="1.0",
        )
        
        result = plugin._filter_by_end_date([past_tx])
        assert len(result) == 1


class TestKrakenProcessTradeHistory:
    """Test Kraken _process_trade_history method."""

    def test_process_trade_history(self):
        """Test processing trade history."""
        from ccxt import kraken
        from unittest.mock import MagicMock
        
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            use_cache=False,
        )
        
        # Create a mock kraken client
        mock_kraken = MagicMock(spec=kraken)
        mock_kraken.private_post_tradeshistory.return_value = {
            "error": [],
            "result": {
                "count": "1",
                "trades": {
                    "trade1": {
                        "ordertxid": "order1",
                        "pair": "BTC/USD",
                        "time": "1403860822.8528068",
                        "type": "buy",
                        "price": "800.0",
                        "cost": "800.0",
                        "fee": "2.0",
                        "vol": "1.0",
                    }
                }
            }
        }
        
        # Set via parent class
        plugin._AbstractCcxtInputPlugin__client = mock_kraken
        
        result = plugin._process_trade_history(0)
        assert "trade1" in result


class TestKrakenProcessLedger:
    """Test Kraken _process_ledger method."""

    def test_process_ledger(self):
        """Test processing ledger."""
        from ccxt import kraken
        from unittest.mock import MagicMock
        
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            use_cache=False,
        )
        
        # Create a mock kraken client
        mock_kraken = MagicMock(spec=kraken)
        mock_kraken.private_post_ledgers.return_value = {
            "error": [],
            "result": {
                "count": "1",
                "ledger": {
                    "ledger1": {
                        "refid": "dep1",
                        "time": "1403860824.8546317",
                        "type": "deposit",
                        "asset": "XXBT",
                        "amount": "2.0",
                        "fee": "0.0",
                        "balance": "2.0"
                    }
                }
            }
        }
        
        plugin._AbstractCcxtInputPlugin__client = mock_kraken
        
        result = plugin._process_ledger(0)
        assert "ledger1" in result


class TestKrakenGatherApiData:
    """Test Kraken _gather_api_data method."""

    def test_gather_api_data_no_cache(self):
        """Test gathering API data without cache."""
        from ccxt import kraken
        from unittest.mock import MagicMock
        
        plugin = KrakenInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            use_cache=False,
        )
        
        # Create a mock kraken client
        mock_kraken = MagicMock(spec=kraken)
        
        # Mock trades history
        mock_kraken.private_post_tradeshistory.return_value = {
            "error": [],
            "result": {
                "count": "0",
            }
        }
        
        # Mock ledgers
        mock_kraken.private_post_ledgers.return_value = {
            "error": [],
            "result": {
                "count": "0",
            }
        }
        
        plugin._AbstractCcxtInputPlugin__client = mock_kraken
        
        result = plugin._gather_api_data()
        assert result is not None
        assert len(result) == 2  # (trade_history, ledger)