# Copyright 2026 eprbell
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

"""Shared utilities for E2E tests.

This module provides common fixtures and mock classes that are reused
across multiple E2E test files to reduce code duplication.
"""

import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


# =============================================================================
# Default Mock Price Constants
# =============================================================================

DEFAULT_MOCK_BTC_USD_PRICE: str = "35000"
DEFAULT_MOCK_ETH_USD_PRICE: str = "2000"
DEFAULT_MOCK_ADA_USD_PRICE: str = "0.35"
DEFAULT_MOCK_USDC_USD_PRICE: str = "1"
DEFAULT_MOCK_USDT_USD_PRICE: str = "1"
DEFAULT_MOCK_EUR_USD_PRICE: str = "1.10"
DEFAULT_MOCK_JPY_USD_PRICE: str = "0.007"


# =============================================================================
# Mock Pair Converter Classes
# =============================================================================

class MockPairConverter:
    """Mock pair converter that returns fixed prices for testing.

    This is the base mock converter that supports common crypto-to-USD
    conversions. It can be configured with custom prices for flexibility.

    Args:
        btc_price: BTC to USD price (default: 35000)
        eth_price: ETH to USD price (default: 2000)
        usdc_price: USDC to USD price (default: 1)
        usdt_price: USDT to USD price (default: 1)
        ada_price: ADA to USD price (default: 0.35)
        xrp_price: XRP to USD price (default: None)
        xlm_price: XLM to USD price (default: None)
        busd_price: BUSD to USD price (default: 1)
    """

    def __init__(
        self,
        btc_price: str = DEFAULT_MOCK_BTC_USD_PRICE,
        eth_price: str = DEFAULT_MOCK_ETH_USD_PRICE,
        usdc_price: str = DEFAULT_MOCK_USDC_USD_PRICE,
        usdt_price: str = DEFAULT_MOCK_USDT_USD_PRICE,
        ada_price: Optional[str] = DEFAULT_MOCK_ADA_USD_PRICE,
        xrp_price: Optional[str] = "0.5",
        xlm_price: Optional[str] = "0.1",
        busd_price: str = "1",
        jpy_price: Optional[str] = "0.007",
        price: Optional[str] = None,  # Legacy parameter for simple ADA-only tests
    ):
        # Support legacy 'price' parameter for simple tests
        if price is not None:
            ada_price = price
        self._btc_price = btc_price
        self._eth_price = eth_price
        self._usdc_price = usdc_price
        self._usdt_price = usdt_price
        self._ada_price = ada_price
        self._xrp_price = xrp_price
        self._xlm_price = xlm_price
        self._busd_price = busd_price
        self._jpy_price = jpy_price
        self._ftm_price = "0.5"  # FTM/FANTOM price
        self._cache: Dict[Any, Any] = {}

    def name(self) -> str:
        return "MockPairConverter"

    def cache_key(self) -> Optional[str]:
        return "mock_converter"

    def get_historic_bar_from_native_source(
        self,
        timestamp: Any,
        from_asset: str,
        to_asset: str,
        exchange: str,
    ) -> Optional[Any]:
        return None

    def get_conversion_rate(
        self,
        timestamp: Any,
        from_asset: str,
        to_asset: str,
        exchange: str,
    ) -> Optional[RP2Decimal]:
        # BTC conversions
        if from_asset == "BTC" and to_asset == "USD":
            return RP2Decimal(self._btc_price)
        if from_asset == "USD" and to_asset == "BTC":
            return RP2Decimal(str(1 / float(self._btc_price)))

        # ETH conversions
        if from_asset == "ETH" and to_asset == "USD":
            return RP2Decimal(self._eth_price)
        if from_asset == "USD" and to_asset == "ETH":
            return RP2Decimal(str(1 / float(self._eth_price)))

        # USDC conversions
        if from_asset == "USDC" and to_asset == "USD":
            return RP2Decimal(self._usdc_price)
        if from_asset == "USD" and to_asset == "USDC":
            return RP2Decimal(str(1 / float(self._usdc_price)))

        # USDT conversions
        if from_asset == "USDT" and to_asset == "USD":
            return RP2Decimal(self._usdt_price)
        if from_asset == "USD" and to_asset == "USDT":
            return RP2Decimal(str(1 / float(self._usdt_price)))

        # BUSD conversions
        if from_asset == "BUSD" and to_asset == "USD":
            return RP2Decimal(self._busd_price)
        if from_asset == "USD" and to_asset == "BUSD":
            return RP2Decimal(str(1 / float(self._busd_price)))

        # ADA conversions
        if self._ada_price is not None:
            if from_asset == "ADA" and to_asset == "USD":
                return RP2Decimal(self._ada_price)
            if from_asset == "USD" and to_asset == "ADA":
                return RP2Decimal(str(1 / float(self._ada_price)))

        # XRP conversions
        if self._xrp_price is not None:
            if from_asset == "XRP" and to_asset == "USD":
                return RP2Decimal(self._xrp_price)
            if from_asset == "USD" and to_asset == "XRP":
                return RP2Decimal(str(1 / float(self._xrp_price)))

        # XLM conversions
        if self._xlm_price is not None:
            if from_asset == "XLM" and to_asset == "USD":
                return RP2Decimal(self._xlm_price)
            if from_asset == "USD" and to_asset == "XLM":
                return RP2Decimal(str(1 / float(self._xlm_price)))

        # JPY conversions
        if self._jpy_price is not None:
            if from_asset == "JPY" and to_asset == "USD":
                return RP2Decimal(self._jpy_price)
            if from_asset == "USD" and to_asset == "JPY":
                return RP2Decimal(str(1 / float(self._jpy_price)))

        # FTM/FANTOM conversions
        if self._ftm_price is not None:
            if from_asset == "FTM" and to_asset == "USD":
                return RP2Decimal(self._ftm_price)
            if from_asset == "USD" and to_asset == "FTM":
                return RP2Decimal(str(1 / float(self._ftm_price)))
            # Handle FANTOM alias
            if from_asset == "FANTOM" and to_asset == "USD":
                return RP2Decimal(self._ftm_price)
            if from_asset == "USD" and to_asset == "FANTOM":
                return RP2Decimal(str(1 / float(self._ftm_price)))

        return None

    def optimize(self, manifest: Any) -> None:
        pass

    def save_historical_price_cache(self) -> None:
        pass

    def load_historical_price_cache(self) -> bool:
        """Mock method - returns False."""
        return False


class MockPairConverterWithPrices:
    """Mock pair converter with a dictionary-based price lookup.

    This variant uses a dictionary for more flexible price configuration
    and supports fiat conversions.

    Args:
        prices: Dictionary mapping (from_asset, to_asset) tuples to RP2Decimal prices.
                Can include None values to test fallback/derivation logic.
        derivation_price: Price to use for derivation (default: 0.05)
    """

    def __init__(
        self,
        prices: Optional[Dict[tuple, Optional[RP2Decimal]]] = None,
        derivation_price: RP2Decimal = RP2Decimal("0.05"),
    ):
        self._prices = prices or {
            ("BTC", "USD"): RP2Decimal("35000"),
            ("ETH", "USD"): RP2Decimal("2000"),
            ("ADA", "USD"): RP2Decimal("0.35"),
            ("EUR", "USD"): RP2Decimal("1.10"),
            ("USD", "EUR"): RP2Decimal("0.909"),
            ("USDT", "USD"): RP2Decimal("1"),
            ("LP", "USD"): RP2Decimal("0"),
            ("LUNC", "USD"): RP2Decimal("0.0001"),
        }
        # Allow None values for testing derivation logic
        if prices is not None:
            self._prices = prices
        self._derivation_price = derivation_price

    def name(self) -> str:
        return "MockPairConverter"

    def cache_key(self) -> Optional[str]:
        return "mock_converter"

    def get_historic_bar_from_native_source(
        self,
        timestamp: Any,
        from_asset: str,
        to_asset: str,
        exchange: str,
    ) -> Optional[Any]:
        return None

    def get_conversion_rate(
        self,
        timestamp: Any,
        from_asset: str,
        to_asset: str,
        exchange: str,
    ) -> Optional[RP2Decimal]:
        # Return the price (which can be None to test fallback/derivation)
        return self._prices.get((from_asset, to_asset))

    def optimize(self, manifest: Any) -> None:
        pass

    def save_historical_price_cache(self) -> None:
        pass

    @property
    def historical_price_type(self) -> str:
        return "mock"


class MockPairConverterWithFiat(MockPairConverterWithPrices):
    """Mock pair converter that supports fiat conversion.

    Extends MockPairConverterWithPrices with fiat conversion support
    for testing currency exchange scenarios.
    """

    def __init__(self):
        super().__init__()
        self._prices = {
            ("BTC", "USD"): RP2Decimal("35000"),
            ("ETH", "USD"): RP2Decimal("2000"),
            ("ADA", "USD"): RP2Decimal("0.35"),
            ("EUR", "USD"): RP2Decimal("1.10"),
            ("USD", "EUR"): RP2Decimal("0.909"),
            ("USDT", "USD"): RP2Decimal("1"),
            ("LP", "USD"): RP2Decimal("0"),  # LP tokens have no market price
        }
        self._derivation_price = RP2Decimal("0.05")  # For MIN token derivation

    def name(self) -> str:
        return "MockFiatPairConverter"

    def cache_key(self) -> Optional[str]:
        return "mock_fiat_converter"


class MockPairConverterFailing:
    """Mock pair converter that always returns None (fails).

    Useful for testing error handling and fallback logic.
    """

    def __init__(self):
        self.call_count = 0

    def name(self) -> str:
        return "MockPairConverterFailing"

    def cache_key(self) -> Optional[str]:
        return "mock_failing"

    def get_historic_bar_from_native_source(
        self,
        timestamp: Any,
        from_asset: str,
        to_asset: str,
        exchange: str,
    ) -> Optional[Any]:
        return None

    def get_conversion_rate(
        self,
        timestamp: Any,
        from_asset: str,
        to_asset: str,
        exchange: str,
    ) -> Optional[RP2Decimal]:
        self.call_count += 1
        return None

    def optimize(self, manifest: Any) -> None:
        pass

    def save_historical_price_cache(self) -> None:
        pass

    @property
    def historical_price_type(self) -> str:
        return "mock_failing"


class MockPairConverterMultiple:
    """Mock pair converter that has multiple converters.

    The first converter fails, allowing testing of fallback logic.

    Args:
        failing_converter: First converter that fails (default: MockPairConverterFailing)
        working_converter: Second converter that works (default: MockPairConverterWithPrices)
    """

    def __init__(
        self,
        failing_converter: Optional[MockPairConverterFailing] = None,
        working_converter: Optional[MockPairConverterWithPrices] = None,
    ):
        self.converter1_failing = failing_converter or MockPairConverterFailing()
        self.converter2_working = working_converter or MockPairConverterWithPrices()

    @property
    def converters(self):
        return [self.converter1_failing, self.converter2_working]


# =============================================================================
# Helper Functions for Transaction Creation
# =============================================================================

def create_in_transaction(
    asset: str = "BTC",
    unique_id: str = "tx123",
    exchange: str = "binance",
    holder: str = "main",
    crypto_in: str = "1.0",
    fiat_in_no_fee: str = "35000",
    timestamp: Optional[datetime] = None,
    spot_price: str = "35000",
    notes: Optional[str] = None,
    fiat_ticker: str = "USD",
    use_crypto_fee: bool = True,
) -> InTransaction:
    """Create an InTransaction for testing."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    if use_crypto_fee:
        return InTransaction(
            plugin="test",
            unique_id=unique_id,
            raw_data="test_data",
            timestamp=str(timestamp),
            asset=asset,
            exchange=exchange,
            holder=holder,
            transaction_type="Buy",
            spot_price=spot_price,
            crypto_in=crypto_in,
            crypto_fee="0.001",
            fiat_in_no_fee=fiat_in_no_fee,
            fiat_in_with_fee=fiat_in_no_fee,
            fiat_fee=None,
            notes=notes,
            fiat_ticker=fiat_ticker,
        )
    else:
        return InTransaction(
            plugin="test",
            unique_id=unique_id,
            raw_data="test_data",
            timestamp=str(timestamp),
            asset=asset,
            exchange=exchange,
            holder=holder,
            transaction_type="Buy",
            spot_price=spot_price,
            crypto_in=crypto_in,
            crypto_fee=None,
            fiat_in_no_fee=fiat_in_no_fee,
            fiat_in_with_fee=fiat_in_no_fee,
            fiat_fee=None,
            notes=notes,
            fiat_ticker=fiat_ticker,
        )


def create_out_transaction(
    asset: str = "BTC",
    unique_id: str = "tx456",
    exchange: str = "binance",
    holder: str = "main",
    crypto_out: str = "1.0",
    fiat_out_no_fee: str = "35000",
    timestamp: Optional[datetime] = None,
    spot_price: str = "35000",
    notes: Optional[str] = None,
    fiat_ticker: str = "USD",
    use_crypto_fee: bool = True,
) -> OutTransaction:
    """Create an OutTransaction for testing."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    if use_crypto_fee:
        return OutTransaction(
            plugin="test",
            unique_id=unique_id,
            raw_data="test_data",
            timestamp=str(timestamp),
            asset=asset,
            exchange=exchange,
            holder=holder,
            transaction_type="Sell",
            spot_price=spot_price,
            crypto_out=crypto_out,
            crypto_fee="0.001",
            fiat_out_no_fee=fiat_out_no_fee,
            fiat_out_with_fee=fiat_out_no_fee,
            fiat_fee=None,
            notes=notes,
            fiat_ticker=fiat_ticker,
        )
    else:
        return OutTransaction(
            plugin="test",
            unique_id=unique_id,
            raw_data="test_data",
            timestamp=str(timestamp),
            asset=asset,
            exchange=exchange,
            holder=holder,
            transaction_type="Sell",
            spot_price=spot_price,
            crypto_out=crypto_out,
            crypto_fee=None,
            fiat_out_no_fee=fiat_out_no_fee,
            fiat_out_with_fee=fiat_out_no_fee,
            fiat_fee=None,
            notes=notes,
            fiat_ticker=fiat_ticker,
        )


# =============================================================================
# Pipeline Helpers
# =============================================================================

def run_dali_pipeline(
    plugin: Any,
    mock_converter: Optional[MockPairConverter] = None,
    native_fiat: str = "USD",
    read_spot_price_from_web: bool = False,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline: load transactions, resolve, return results."""
    transactions = plugin.load(US())
    if mock_converter is None:
        mock_converter = MockPairConverter()

    dali_configuration = {
        Keyword.NATIVE_FIAT.value: native_fiat,
        Keyword.HISTORICAL_PAIR_CONVERTERS.value: [mock_converter],
    }

    resolved_transactions = resolve_transactions(
        transactions,
        dali_configuration,
        read_spot_price_from_web=read_spot_price_from_web,
    )
    return resolved_transactions


def run_dali_pipeline_with_config(
    plugin: Any,
    configuration: Dict[str, Any],
    read_spot_price_from_web: bool = False,
) -> List[AbstractTransaction]:
    """Run the DALI pipeline with a custom configuration."""
    transactions = plugin.load(US())
    resolved_transactions = resolve_transactions(
        transactions,
        configuration,
        read_spot_price_from_web=read_spot_price_from_web,
    )
    return resolved_transactions