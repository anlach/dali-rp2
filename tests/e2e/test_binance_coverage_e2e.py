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

"""E2E tests for Binance.com REST plugin to improve coverage.

These tests focus on the uncovered methods in binance_com.py including:
- _process_gains (dividends, staking, savings, mining)
- _process_implicit_api (fiat payments, deposits, withdrawals, dust trades)
- _process_dust_trade
- _process_fiat_order
- _process_fiat_payment
"""

import json
from datetime import datetime
from typing import Any, Dict
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from ccxt import binance

from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.out_transaction import OutTransaction

# Import the REST plugin
from dali.plugin.input.rest.binance_com import InputPlugin as BinanceComInputPlugin


class TestBinanceProcessGains:
    """Test Binance _process_gains method (lines 244-575)."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin with mocked client."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        mock_client = MagicMock(spec=binance)
        plugin._AbstractCcxtInputPlugin__client = mock_client
        mock_client.fetch_markets.return_value = [{"id": "BTC/USDT", "type": "spot"}]
        plugin._AbstractCcxtInputPlugin__markets = []
        return plugin

    def test_process_gains_with_dividends(self, binance_plugin):
        """Test _process_gains with dividend data."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        # Mock sapiGetAssetAssetDividend response
        mock_client.sapiGetAssetAssetDividend.return_value = {
            "rows": [
                {
                    "id": "1637366104",
                    "amount": "10.00000000",
                    "asset": "BTC",
                    "divTime": "1563189166000",
                    "enInfo": "BHFT distribution",
                    "tranId": "2968885920"
                }
            ],
            "total": "1"
        }
        
        in_transactions = []
        out_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2020, 1, 1)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2020, 1, 1)
            
            plugin._process_gains(in_transactions, out_transactions)
        
        assert len(in_transactions) > 0

    def test_process_gains_with_staking(self, binance_plugin):
        """Test _process_gains with locked staking data."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        mock_client.sapiGetAssetAssetDividend.return_value = {"rows": [], "total": "0"}
        mock_client.sapi_get_staking_stakingrecord.return_value = [
            {
                "positionId": "7146912",
                "time": "1624233772000",
                "asset": "BTC",
                "amount": "0.017666",
                "status": "SUCCESS"
            }
        ]
        
        in_transactions = []
        out_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2021, 7, 15)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2021, 7, 15)
            
            plugin._process_gains(in_transactions, out_transactions)

    def test_process_gains_with_mining(self, binance_plugin):
        """Test _process_gains with mining income."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        mock_client.sapiGetAssetAssetDividend.return_value = {"rows": [], "total": "0"}
        mock_client.sapi_get_staking_stakingrecord.return_value = []
        
        # Add username to enable mining
        plugin_with_username = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            username="test_miner",
        )
        mock_client2 = MagicMock(spec=binance)
        mock_client2.fetch_markets.return_value = [{"id": "BTC/USDT", "type": "spot"}]
        plugin_with_username._AbstractCcxtInputPlugin__client = mock_client2
        plugin_with_username._AbstractCcxtInputPlugin__markets = []
        plugin_with_username._InputPlugin__algos = ["SHA256"]
        
        mock_client2.sapiGetMiningPaymentList.return_value = {
            "data": {
                "accountProfits": [
                    {
                        "time": "1586188800000",
                        "type": "0",
                        "profitAmount": "8.6083060304",
                        "coinName": "BTC",
                        "status": "2"
                    }
                ],
                "totalNum": "1",
                "pageSize": "200"
            }
        }
        
        in_transactions = []
        out_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2020, 4, 15)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2020, 4, 15)
            
            plugin_with_username._process_gains(in_transactions, out_transactions)


class TestBinanceProcessImplicitApi:
    """Test Binance _process_implicit_api method (lines 584-743)."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin with mocked client."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        mock_client = MagicMock(spec=binance)
        mock_client.fetch_markets.return_value = [{"id": "BTC/USDT", "type": "spot"}]
        plugin._AbstractCcxtInputPlugin__client = mock_client
        plugin._AbstractCcxtInputPlugin__markets = []
        return plugin

    def test_process_implicit_api_fiat_payments(self, binance_plugin):
        """Test _process_implicit_api with fiat payments."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        mock_client.sapiGetFiatPayments.return_value = {
            "data": [
                {
                    "orderNo": "353fca443f06466db0c4dc89f94f027a",
                    "sourceAmount": "20.0",
                    "fiatCurrency": "EUR",
                    "obtainAmount": "4.462",
                    "cryptoCurrency": "LUNA",
                    "totalFee": "0.2",
                    "price": "4.437472",
                    "status": "Completed",
                    "createTime": "1624529919000",
                    "updateTime": "1624529919000"
                }
            ]
        }
        mock_client.sapiGetFiatOrders.return_value = {"data": []}
        mock_client.fetch_my_dust_trades.return_value = []
        
        in_transactions = []
        out_transactions = []
        intra_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2021, 7, 1)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2021, 7, 1)
            
            plugin._process_implicit_api(in_transactions, out_transactions, intra_transactions)

    def test_process_implicit_api_fiat_deposits(self, binance_plugin):
        """Test _process_implicit_api with fiat deposits."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        mock_client.sapiGetFiatPayments.return_value = {"data": []}
        mock_client.sapiGetFiatOrders.return_value = {
            "data": [
                {
                    "orderNo": "25ced37075c1470ba8939d0df2316e23",
                    "fiatCurrency": "EUR",
                    "indicatedAmount": "15.00",
                    "amount": "15.00",
                    "totalFee": "0.00",
                    "method": "Card",
                    "status": "Successful",
                    "createTime": "1627501026000",
                    "updateTime": "1627501027000"
                }
            ]
        }
        mock_client.fetch_my_dust_trades.return_value = []
        
        in_transactions = []
        out_transactions = []
        intra_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2021, 8, 1)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2021, 8, 1)
            
            plugin._process_implicit_api(in_transactions, out_transactions, intra_transactions)

    def test_process_implicit_api_fiat_withdrawals(self, binance_plugin):
        """Test _process_implicit_api with fiat withdrawals."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        mock_client.sapiGetFiatPayments.return_value = {"data": []}
        mock_client.sapiGetFiatOrders.side_effect = [
            {"data": []},
            {
                "data": [
                    {
                        "orderNo": "withdraw123",
                        "fiatCurrency": "EUR",
                        "indicatedAmount": "100.00",
                        "amount": "100.00",
                        "totalFee": "1.00",
                        "method": "Card",
                        "status": "Successful",
                        "createTime": "1627501026000",
                        "updateTime": "1627501027000"
                    }
                ]
            }
        ]
        mock_client.fetch_my_dust_trades.return_value = []
        
        in_transactions = []
        out_transactions = []
        intra_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2021, 8, 1)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2021, 8, 1)
            
            plugin._process_implicit_api(in_transactions, out_transactions, intra_transactions)
        
        assert len(out_transactions) > 0

    def test_process_implicit_api_dust_trades(self, binance_plugin):
        """Test _process_implicit_api with dust trades."""
        plugin = binance_plugin
        mock_client = plugin._AbstractCcxtInputPlugin__client
        
        mock_client.sapiGetFiatPayments.return_value = {"data": []}
        mock_client.sapiGetFiatOrders.return_value = {"data": []}
        mock_client.fetch_my_dust_trades.return_value = [
            {
                "info": {},
                "id": None,
                "timestamp": 1624233772000,
                "datetime": "2021-06-21T00:00:00.000Z",
                "symbol": "BTC/USDT",
                "order": "12345",
                "type": None,
                "side": "buy",
                "takerOrMaker": "taker",
                "price": "35000",
                "amount": "0.001",
                "cost": "35",
                "fee": {"cost": "0.0001", "currency": "BNB"}
            }
        ]
        
        in_transactions = []
        out_transactions = []
        intra_transactions = []
        
        with patch('dali.plugin.input.rest.binance_com.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2021, 8, 1)
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            mock_datetime.fromtimestamp.return_value = datetime(2021, 8, 1)
            
            plugin._process_implicit_api(in_transactions, out_transactions, intra_transactions)


class TestBinanceProcessDustTrade:
    """Test Binance _process_dust_trade method."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin."""
        return BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_process_dust_trade_bnb_base(self, binance_plugin):
        """Test dust trade with BNB as quote asset."""
        plugin = binance_plugin
        
        dust = {
            "symbol": "BTC/BNB",
            "amount": "0.001",
            "cost": "0.01",
            "order": "12345",
            "side": "buy",
            "timestamp": 1624233772000,
            "divTime": "1624233772000",
            "fee": {"cost": "0.0001", "currency": "BNB"}
        }
        
        result = plugin._process_dust_trade(dust)
        assert result is not None

    def test_process_dust_trade_bnb_quote(self, binance_plugin):
        """Test dust trade with BNB as quote asset."""
        plugin = binance_plugin
        
        dust = {
            "symbol": "ETH/BNB",
            "amount": "0.01",
            "cost": "0.5",
            "order": "12345",
            "side": "buy",
            "timestamp": 1624233772000,
            "divTime": "1624233772000",
            "fee": {"cost": "0.001", "currency": "BNB"}
        }
        
        result = plugin._process_dust_trade(dust)
        assert result is not None


class TestBinanceProcessFiatOrder:
    """Test Binance fiat order processing methods."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin."""
        return BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_process_fiat_deposit_order_successful(self, binance_plugin):
        """Test processing successful fiat deposit order."""
        plugin = binance_plugin
        
        transaction = {
            "orderNo": "test123",
            "fiatCurrency": "EUR",
            "indicatedAmount": "100.00",
            "amount": "100.00",
            "totalFee": "1.00",
            "method": "Card",
            "status": "Successful",
            "createTime": "1627501026000",
            "updateTime": "1627501027000"
        }
        
        result = plugin._process_fiat_deposit_order(transaction)
        assert len(result.in_transactions) > 0

    def test_process_fiat_deposit_order_failed(self, binance_plugin):
        """Test processing failed fiat deposit order."""
        plugin = binance_plugin
        
        transaction = {
            "orderNo": "test123",
            "fiatCurrency": "EUR",
            "indicatedAmount": "100.00",
            "amount": "100.00",
            "totalFee": "1.00",
            "method": "Card",
            "status": "Failed",
            "createTime": "1627501026000",
            "updateTime": "1627501027000"
        }
        
        result = plugin._process_fiat_deposit_order(transaction)
        assert len(result.in_transactions) == 0

    def test_process_fiat_withdrawal_order_successful(self, binance_plugin):
        """Test processing successful fiat withdrawal order."""
        plugin = binance_plugin
        
        transaction = {
            "orderNo": "withdraw123",
            "fiatCurrency": "EUR",
            "indicatedAmount": "50.00",
            "amount": "50.00",
            "totalFee": "0.50",
            "method": "Card",
            "status": "Successful",
            "createTime": "1627501026000",
            "updateTime": "1627501027000"
        }
        
        result = plugin._process_fiat_withdrawal_order(transaction)
        assert len(result.out_transactions) > 0


class TestBinanceProcessFiatPayment:
    """Test Binance fiat payment processing."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin."""
        return BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_process_fiat_payment_completed_native(self, binance_plugin):
        """Test processing completed fiat payment with native fiat."""
        plugin = binance_plugin
        
        transaction = {
            "orderNo": "payment123",
            "sourceAmount": "100.0",
            "fiatCurrency": "USD",
            "obtainAmount": "0.01",
            "cryptoCurrency": "BTC",
            "totalFee": "1.0",
            "price": "10000",
            "status": "Completed",
            "createTime": "1624529919000",
            "updateTime": "1624529919000"
        }
        
        result = plugin._process_fiat_payment(transaction)
        assert len(result.in_transactions) >= 2

    def test_process_fiat_payment_completed_non_native(self, binance_plugin):
        """Test processing completed fiat payment with non-native fiat."""
        plugin = binance_plugin
        
        transaction = {
            "orderNo": "payment123",
            "sourceAmount": "100.0",
            "fiatCurrency": "EUR",
            "obtainAmount": "0.01",
            "cryptoCurrency": "BTC",
            "totalFee": "1.0",
            "price": "10000",
            "status": "Completed",
            "createTime": "1624529919000",
            "updateTime": "1624529919000"
        }
        
        result = plugin._process_fiat_payment(transaction)
        assert len(result.in_transactions) >= 2
        assert len(result.out_transactions) >= 1

    def test_process_fiat_payment_failed(self, binance_plugin):
        """Test processing failed fiat payment."""
        plugin = binance_plugin
        
        transaction = {
            "orderNo": "payment123",
            "sourceAmount": "100.0",
            "fiatCurrency": "USD",
            "obtainAmount": "0.01",
            "cryptoCurrency": "BTC",
            "totalFee": "1.0",
            "price": "10000",
            "status": "Failed",
            "createTime": "1624529919000",
            "updateTime": "1624529919000"
        }
        
        result = plugin._process_fiat_payment(transaction)
        assert len(result.in_transactions) == 0


class TestBinanceAlgosWithUsername:
    """Test Binance algo fetching with username."""

    def test_get_algos_with_username(self):
        """Test getting algos with username from API."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
            username="test_miner",
        )
        
        mock_client = MagicMock(spec=binance)
        mock_client.fetch_markets.return_value = [{"id": "BTC/USDT", "type": "spot"}]
        mock_client.sapiGetMiningPubAlgoList.return_value = {
            "data": [
                {"algoName": "SHA256"},
                {"algoName": "Ethash"}
            ]
        }
        
        plugin._AbstractCcxtInputPlugin__client = mock_client
        plugin._AbstractCcxtInputPlugin__markets = []
        
        result = plugin._get_algos()
        
        assert "SHA256" in result
        assert "Ethash" in result


class TestBinanceClientProperty:
    """Test Binance _client property validation."""

    def test_client_property_valid(self):
        """Test _client property with valid binance client."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        mock_client = MagicMock(spec=binance)
        mock_client.fetch_markets.return_value = [{"id": "BTC/USDT", "type": "spot"}]
        plugin._AbstractCcxtInputPlugin__client = mock_client
        plugin._AbstractCcxtInputPlugin__markets = []
        
        client = plugin._client
        assert client is mock_client

    def test_client_property_invalid(self):
        """Test _client property with invalid client raises error."""
        plugin = BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )
        
        plugin._AbstractCcxtInputPlugin__client = MagicMock()
        
        from rp2.rp2_error import RP2RuntimeError
        with pytest.raises(RP2RuntimeError):
            _ = plugin._client


class TestBinanceUnrecognizedDividend:
    """Test handling of unrecognized dividend types."""

    @pytest.fixture
    def binance_plugin(self):
        """Create a Binance plugin."""
        return BinanceComInputPlugin(
            account_holder="test_user",
            api_key="test_key",
            api_secret="test_secret",
            native_fiat="USD",
        )

    def test_process_dividend_unrecognized(self, binance_plugin):
        """Test processing unrecognized dividend type logs error."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "UnknownType12345",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)
        assert len(result.in_transactions) == 0

    def test_process_dividend_airdrop_regex(self, binance_plugin):
        """Test dividend processing with airdrop regex match."""
        plugin = binance_plugin
        
        dividend = {
            "id": "1637366104",
            "amount": "10.00000000",
            "asset": "BTC",
            "divTime": "1563189166000",
            "enInfo": "Test airdrop event",
            "tranId": "2968885920"
        }
        
        result = plugin._process_dividend(dividend)
        assert result is not None
