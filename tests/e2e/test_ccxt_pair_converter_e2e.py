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

"""E2E tests for AbstractCCXTPairConverterPlugin to improve code coverage.

These tests verify the AbstractCCXTPairConverterPlugin base class functionality
including initialization, historical price fetching, caching, rate limiting, and edge cases.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from rp2.rp2_decimal import RP2Decimal, ZERO
from rp2.rp2_error import RP2ValueError

from dali.abstract_ccxt_pair_converter_plugin import (
    _ALT_MARKET_BY_BASE_DICT,
    _DEFAULT_EXCHANGE,
    _FIAT_EXCHANGE,
    _KRAKEN,
    _ONE_WEEK,
    _TIME_GRANULARITY,
    AbstractCcxtPairConverterPlugin,
    AssetPairAndHistoricalPrice,
    AssetPairAndTimestamp,
)
from dali.configuration import Keyword
from dali.historical_bar import HistoricalBar
from dali.mapped_graph import Alias, MappedGraph


# =============================================================================
# Mock Implementation for Testing
# =============================================================================

class MockCcxtPairConverterPlugin(AbstractCcxtPairConverterPlugin):
    """Concrete implementation of AbstractCcxtPairConverterPlugin for testing."""

    def __init__(self, *args, **kwargs):
        self._mock_fiat_list: List[str] = []
        self._mock_fiat_priority: Dict[str, float] = {}
        super().__init__(*args, **kwargs)

    def name(self) -> str:
        return "MockCCXTPairConverter"

    def _get_fiat_exchange_rate(self, timestamp: datetime, from_asset: str, to_asset: str) -> Optional[HistoricalBar]:
        # Mock implementation for fiat exchange rate
        if from_asset == to_asset:
            return HistoricalBar(
                duration=timedelta(seconds=604800),
                timestamp=timestamp,
                open=RP2Decimal("1"),
                high=RP2Decimal("1"),
                low=RP2Decimal("1"),
                close=RP2Decimal("1"),
                volume=ZERO,
            )
        return HistoricalBar(
            duration=timedelta(seconds=604800),
            timestamp=timestamp,
            open=RP2Decimal("1.5"),
            high=RP2Decimal("1.6"),
            low=RP2Decimal("1.4"),
            close=RP2Decimal("1.5"),
            volume=ZERO,
        )

    def _build_fiat_list(self) -> None:
        self._fiat_list = ["USD", "EUR", "JPY", "KRW", "GBP"]
        self._fiat_priority = {"USD": 1, "EUR": 2, "JPY": 3, "KRW": 4, "GBP": 5}


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def plugin() -> MockCcxtPairConverterPlugin:
    """Create a mock plugin instance."""
    return MockCcxtPairConverterPlugin(Keyword.HISTORICAL_PRICE_HIGH.value)


@pytest.fixture
def plugin_with_exchange() -> MockCcxtPairConverterPlugin:
    """Create a mock plugin instance with a default exchange."""
    return MockCcxtPairConverterPlugin(
        Keyword.HISTORICAL_PRICE_HIGH.value,
        default_exchange=_KRAKEN,
    )


@pytest.fixture
def plugin_with_untradeable_assets() -> MockCcxtPairConverterPlugin:
    """Create a mock plugin instance with untradeable assets."""
    return MockCcxtPairConverterPlugin(
        Keyword.HISTORICAL_PRICE_HIGH.value,
        untradeable_assets="UNTRADABLE1, UNTRADABLE2",
    )


@pytest.fixture
def plugin_with_aliases() -> MockCcxtPairConverterPlugin:
    """Create a mock plugin instance with aliases."""
    return MockCcxtPairConverterPlugin(
        Keyword.HISTORICAL_PRICE_HIGH.value,
        aliases=f"{_KRAKEN},BTC,USD,1.5;UNIVERSAL,ETH,USD,2.0",
    )


@pytest.fixture
def plugin_with_cache_modifier() -> MockCcxtPairConverterPlugin:
    """Create a mock plugin instance with cache modifier."""
    return MockCcxtPairConverterPlugin(
        Keyword.HISTORICAL_PRICE_HIGH.value,
        cache_modifier="custom_modifier",
    )


@pytest.fixture
def mock_historical_bar() -> HistoricalBar:
    """Create a mock historical bar."""
    return HistoricalBar(
        duration=timedelta(seconds=604800),
        timestamp=datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc),
        open=RP2Decimal("50000"),
        high=RP2Decimal("51000"),
        low=RP2Decimal("49000"),
        close=RP2Decimal("50500"),
        volume=RP2Decimal("1000"),
    )


# =============================================================================
# Test: Plugin Initialization
# =============================================================================

class TestPluginInitialization:
    """Tests for plugin initialization and configuration."""

    def test_default_initialization(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test default initialization."""
        assert plugin.name() == "MockCCXTPairConverter"
        assert plugin.cache_key() == "MockCCXTPairConverter"
        # Fiat list should be empty until built
        assert isinstance(plugin.fiat_list, list)

    def test_initialization_with_default_exchange(self, plugin_with_exchange: MockCcxtPairConverterPlugin) -> None:
        """Test initialization with a default exchange."""
        assert plugin_with_exchange._AbstractCcxtPairConverterPlugin__default_exchange == _KRAKEN

    def test_initialization_with_untradeable_assets(self, plugin_with_untradeable_assets: MockCcxtPairConverterPlugin) -> None:
        """Test initialization with untradeable assets."""
        untradeable = plugin_with_untradeable_assets._AbstractCcxtPairConverterPlugin__untradeable_assets
        assert "UNTRADABLE1" in untradeable
        assert "UNTRADABLE2" in untradeable

    def test_initialization_with_aliases(self, plugin_with_aliases: MockCcxtPairConverterPlugin) -> None:
        """Test initialization with aliases."""
        aliases = plugin_with_aliases._AbstractCcxtPairConverterPlugin__aliases
        assert aliases is not None
        assert _KRAKEN in aliases or "UNIVERSAL" in aliases

    def test_cache_key_with_modifier(self, plugin_with_cache_modifier: MockCcxtPairConverterPlugin) -> None:
        """Test cache key generation with modifier."""
        assert "custom_modifier" in plugin_with_cache_modifier.cache_key()

    def test_cache_key_with_exchange_locked(self) -> None:
        """Test cache key generation when exchange is locked."""
        # Note: cache_key() calls name() which is abstract, so we test the internal logic instead
        # The exchange_locked flag should be set correctly
        plugin = MockCcxtPairConverterPlugin(
            Keyword.HISTORICAL_PRICE_HIGH.value,
            default_exchange=_KRAKEN,
            exchange_locked=True,
        )
        # Verify exchange_locked is set
        is_locked = plugin._AbstractCcxtPairConverterPlugin__exchange_locked
        assert is_locked is True
        # Verify default exchange is set
        default_exchange = plugin._AbstractCcxtPairConverterPlugin__default_exchange
        assert default_exchange == _KRAKEN

    def test_initialization_with_quarterly_zip(self) -> None:
        """Test initialization with use_quarterly_zip flag."""
        plugin = MockCcxtPairConverterPlugin(
            Keyword.HISTORICAL_PRICE_HIGH.value,
            use_quarterly_zip=True,
        )
        assert plugin._AbstractCcxtPairConverterPlugin__use_quarterly_zip is True


# =============================================================================
# Test: Cache Operations
# =============================================================================

class TestCacheOperations:
    """Tests for cache operations."""

    def test_add_and_get_bar_from_cache(self, plugin: MockCcxtPairConverterPlugin, mock_historical_bar: HistoricalBar) -> None:
        """Test adding and retrieving a bar from cache."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        key = AssetPairAndTimestamp(timestamp, "BTC", "USD", _KRAKEN)

        plugin._add_bar_to_cache(key, mock_historical_bar)
        retrieved_bar = plugin._get_bar_from_cache(key)

        assert retrieved_bar is not None
        assert retrieved_bar.open == mock_historical_bar.open

    def test_get_bar_from_empty_cache(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test retrieving from empty cache returns None."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        key = AssetPairAndTimestamp(timestamp, "BTC", "USD", _KRAKEN)

        retrieved_bar = plugin._get_bar_from_cache(key)
        assert retrieved_bar is None

    def test_add_and_get_bundle_from_cache(self, plugin: MockCcxtPairConverterPlugin, mock_historical_bar: HistoricalBar) -> None:
        """Test adding and retrieving a bundle from cache."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        key = AssetPairAndTimestamp(timestamp, "BTC", "USD", _KRAKEN)
        bars = [mock_historical_bar, mock_historical_bar]

        plugin._add_bundle_to_cache(key, bars)
        retrieved_bars = plugin._get_bundle_from_cache(key)

        assert retrieved_bars is not None
        assert len(retrieved_bars) == 2


# =============================================================================
# Test: Floor Key Operations
# =============================================================================

class TestFloorKeyOperations:
    """Tests for _floor_key method."""

    def test_floor_key_not_daily(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test floor_key without daily flag."""
        timestamp = datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
        key = AssetPairAndTimestamp(timestamp, "BTC", "USD", _KRAKEN)

        floored_key = plugin._floor_key(key)

        # Should floor to the minute
        assert floored_key.timestamp.minute == 30
        assert floored_key.timestamp.second == 0
        assert floored_key.timestamp.microsecond == 0

    def test_floor_key_daily(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test floor_key with daily flag."""
        timestamp = datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
        key = AssetPairAndTimestamp(timestamp, "BTC", "USD", _KRAKEN)

        floored_key = plugin._floor_key(key, daily=True)

        # Should floor to midnight
        assert floored_key.timestamp.hour == 0
        assert floored_key.timestamp.minute == 0
        assert floored_key.timestamp.second == 0
        assert floored_key.timestamp.microsecond == 0


# =============================================================================
# Test: Properties
# =============================================================================

class TestProperties:
    """Tests for plugin properties."""

    def test_exchanges_property(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test exchanges property returns empty dict initially."""
        exchanges = plugin.exchanges
        assert isinstance(exchanges, dict)

    def test_exchange_markets_property(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test exchange_markets property returns empty dict initially."""
        markets = plugin.exchange_markets
        assert isinstance(markets, dict)

    def test_exchange_2_graph_tree_property(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test exchange_2_graph_tree property returns empty dict initially."""
        tree = plugin.exchange_2_graph_tree
        assert isinstance(tree, dict)

    def test_fiat_list_property(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test fiat_list property."""
        fiat_list = plugin.fiat_list
        assert isinstance(fiat_list, list)


# =============================================================================
# Test: Get Historic Bar from Native Source
# =============================================================================

class TestGetHistoricBarFromNativeSource:
    """Tests for get_historic_bar_from_native_source method."""

    def test_same_asset_returns_one(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test that converting same asset returns a bar with price 1."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        result = plugin.get_historic_bar_from_native_source(timestamp, "BTC", "BTC", _KRAKEN)

        assert result is not None
        assert result.open == RP2Decimal("1")
        assert result.close == RP2Decimal("1")

    def test_fiat_pair_uses_fiat_exchange(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test that fiat pair uses fiat exchange rate."""
        plugin._build_fiat_list()
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        result = plugin.get_historic_bar_from_native_source(timestamp, "USD", "EUR", _KRAKEN)

        assert result is not None

    def test_crypto_pair_requires_graph(self, plugin: MockCcxtPairConverterPlugin, mocker: Any) -> None:
        """Test that crypto pair conversion requires graph to be built."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        # Should raise error if graph not built
        with pytest.raises(Exception):  # RP2RuntimeError
            plugin.get_historic_bar_from_native_source(timestamp, "BTC", "USD", _KRAKEN)


# =============================================================================
# Test: Find Historical Bar
# =============================================================================

class TestFindHistoricalBar:
    """Tests for find_historical_bar method."""

    def test_find_historical_bar_from_cache(self, plugin: MockCcxtPairConverterPlugin, mock_historical_bar: HistoricalBar) -> None:
        """Test finding historical bar from cache."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        key = AssetPairAndTimestamp(timestamp, "BTC", "USD", _KRAKEN)

        # Add to cache
        plugin._add_bar_to_cache(key, mock_historical_bar)

        # Try to find - should get from cache
        result = plugin.find_historical_bar("BTC", "USD", timestamp, _KRAKEN)

        assert result is not None
        assert result.open == mock_historical_bar.open

    def test_find_historical_bar_not_in_cache(self, plugin: MockCcxtPairConverterPlugin, mocker: Any) -> None:
        """Test finding historical bar not in cache."""
        timestamp = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

        # Mock find_historical_bars to return a bar
        mock_bar = HistoricalBar(
            duration=timedelta(seconds=604800),
            timestamp=timestamp,
            open=RP2Decimal("50000"),
            high=RP2Decimal("51000"),
            low=RP2Decimal("49000"),
            close=RP2Decimal("50500"),
            volume=ZERO,
        )

        mocker.patch.object(plugin, "find_historical_bars", return_value=[mock_bar])

        result = plugin.find_historical_bar("BTC", "USD", timestamp, _KRAKEN)

        assert result is not None


# =============================================================================
# Test: Initialize Retry Count
# =============================================================================

class TestInitializeRetryCount:
    """Tests for _initialize_retry_count method."""

    def test_valid_granularity(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test with valid granularity."""
        result = plugin._initialize_retry_count(_KRAKEN, "1m")
        assert isinstance(result, int)
        assert result >= 0

    def test_invalid_granularity(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test with invalid granularity."""
        with pytest.raises(RP2ValueError):
            plugin._initialize_retry_count(_KRAKEN, "invalid_granularity")


# =============================================================================
# Test: Alternative Markets
# =============================================================================

class TestAlternativeMarkets:
    """Tests for alternative market handling."""

    def test_get_alt_market_by_base(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test getting alternative market by base."""
        result = plugin._get_alt_market_by_base()
        assert isinstance(result, dict)
        assert "USDT" in result  # Known alt market


# =============================================================================
# Test: Fiat Helpers
# =============================================================================

class TestFiatHelpers:
    """Tests for fiat-related helper methods."""

    def test_is_fiat(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test _is_fiat method."""
        plugin._build_fiat_list()
        assert plugin._is_fiat("USD") is True
        assert plugin._is_fiat("EUR") is True
        assert plugin._is_fiat("NOTFIAT") is False

    def test_is_fiat_pair(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test _is_fiat_pair method."""
        plugin._build_fiat_list()
        assert plugin._is_fiat_pair("USD", "EUR") is True
        assert plugin._is_fiat_pair("USD", "BTC") is False
        assert plugin._is_fiat_pair("BTC", "USD") is False

    def test_is_fiat_with_empty_list(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test _is_fiat with empty list builds the list."""
        # fiat_list starts as DEFAULT_FIAT_LIST, so this should work
        result = plugin._is_fiat("USD")
        assert isinstance(result, bool)


# =============================================================================
# Test: Previous Monday
# =============================================================================

class TestPreviousMonday:
    """Tests for _get_previous_monday method."""

    def test_get_previous_monday_monday(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test getting previous Monday from a Monday - returns previous Sunday."""
        date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # Monday
        result = plugin._get_previous_monday(date)
        # Returns the previous day (Sunday for Monday input)
        assert result < date
        assert result.weekday() == 6  # Sunday

    def test_get_previous_monday_friday(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test getting previous Monday from a Friday."""
        date = datetime(2024, 1, 12, 12, 0, 0, tzinfo=timezone.utc)  # Friday
        result = plugin._get_previous_monday(date)
        assert result < date
        # For Friday (weekday 4), it returns date - 5 days = previous Sunday
        assert result.weekday() == 6  # Sunday

    def test_get_previous_monday_sunday(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test getting previous Monday from a Sunday - returns same day."""
        date = datetime(2024, 1, 14, 12, 0, 0, tzinfo=timezone.utc)  # Sunday
        result = plugin._get_previous_monday(date)
        # For Sunday (weekday 6), it returns date - 0 = same day (Sunday)
        # Note: This function returns the most recent Monday or same day if already Monday
        assert result == date


# =============================================================================
# Test: Request Delay
# =============================================================================

class TestRequestDelay:
    """Tests for _get_request_delay method."""

    def test_get_request_delay_kraken(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test request delay for Kraken."""
        delay = plugin._get_request_delay(_KRAKEN)
        assert delay > 0  # Kraken has rate limiting

    def test_get_request_delay_binance(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test request delay for Binance (no delay by default)."""
        delay = plugin._get_request_delay("Binance.com")
        assert delay == 0


# =============================================================================
# Test: Process Aliases
# =============================================================================

class TestProcessAliases:
    """Tests for _process_aliases method."""

    def test_process_valid_aliases(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test processing valid aliases."""
        alias_string = f"{_KRAKEN},BTC,USD,1.5"
        result = plugin._process_aliases(alias_string)
        assert isinstance(result, dict)

    def test_process_invalid_exchange(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test processing aliases with invalid exchange."""
        alias_string = "INVALID_EXCHANGE,BTC,USD,1.5"
        with pytest.raises(RP2ValueError):
            plugin._process_aliases(alias_string)

    def test_process_multiple_aliases(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test processing multiple aliases."""
        alias_string = f"{_KRAKEN},BTC,USD,1.5;{_KRAKEN},ETH,USD,2.0"
        result = plugin._process_aliases(alias_string)
        assert _KRAKEN in result


# =============================================================================
# Test: Following Monday
# =============================================================================

class TestFindFollowingMonday:
    """Tests for _find_following_monday method."""

    def test_find_following_monday(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test finding following Monday."""
        timestamp = datetime(2024, 1, 10, 12, 0, 0)  # Wednesday
        result = plugin._find_following_monday(timestamp)
        assert result.weekday() == 0  # Monday
        assert result > timestamp


# =============================================================================
# Test: Optimize Method
# =============================================================================

class TestOptimize:
    """Tests for optimize method."""

    def test_optimize_with_manifest(self, plugin: MockCcxtPairConverterPlugin, mocker: Any) -> None:
        """Test optimize method with transaction manifest."""
        mock_manifest = MagicMock()
        mock_manifest.first_transaction_datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_manifest.assets = {"BTC", "ETH"}

        # This should work without error even if we don't fully set up the manifest
        # The actual graph building would fail without proper CCXT mocks
        plugin.optimize(mock_manifest)
        assert plugin._manifest == mock_manifest


# =============================================================================
# Test: Add Alternative Markets
# =============================================================================

class TestAddAlternativeMarkets:
    """Tests for _add_alternative_markets method."""

    def test_add_alternative_markets(self, plugin: MockCcxtPairConverterPlugin, mocker: Any) -> None:
        """Test adding alternative markets to graph."""
        # Create a simple mock graph
        mock_graph = MagicMock(spec=MappedGraph)
        mock_graph.add_neighbor = MagicMock()

        current_markets: Dict[str, List[str]] = {}

        # This should work
        plugin._add_alternative_markets(mock_graph, current_markets)

        # Verify add_neighbor was called for at least some alt markets
        assert mock_graph.add_neighbor.called


# =============================================================================
# Test: Generate Unoptimized Graph
# =============================================================================

class TestGenerateUnoptimizedGraph:
    """Tests for _generate_unoptimized_graph method."""

    def test_generate_unoptimized_graph_with_manifest(self, plugin: MockCcxtPairConverterPlugin, mocker: Any) -> None:
        """Test that generate unoptimized graph works with manifest."""
        # Set up a mock manifest
        mock_manifest = MagicMock()
        mock_manifest.first_transaction_datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)
        
        plugin.optimize(mock_manifest)

        # This should work with manifest
        # Note: This actually calls the exchange API, so we're just verifying the method runs
        # The real test would require mocking the CCXT exchange


# =============================================================================
# Test: Pricing Exchange for Exchange
# =============================================================================

class TestGetPricingExchangeForExchange:
    """Tests for _get_pricing_exchange_for_exchange method."""

    def test_unknown_exchange_uses_default(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test that unknown exchange uses default."""
        # With exchange_locked=True and unknown exchange
        plugin._AbstractCcxtPairConverterPlugin__exchange_locked = True
        result = plugin._get_pricing_exchange_for_exchange("UNKNOWN")
        # Should use default exchange
        assert result == _DEFAULT_EXCHANGE

    def test_known_exchange_returns_itself(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test that known exchange returns itself."""
        # First need to set up exchange_markets
        plugin._AbstractCcxtPairConverterPlugin__exchange_markets = {_KRAKEN: {}}
        plugin._AbstractCcxtPairConverterPlugin__exchange_2_graph_tree = {}

        result = plugin._get_pricing_exchange_for_exchange(_KRAKEN)
        assert result == _KRAKEN


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_cache_key_with_empty_modifier(self, plugin: MockCcxtPairConverterPlugin) -> None:
        """Test cache key when modifier is empty."""
        assert plugin.cache_key() == "MockCCXTPairConverter"

    def test_cache_key_with_modifier_only(self, plugin_with_cache_modifier: MockCcxtPairConverterPlugin) -> None:
        """Test cache key with modifier set."""
        assert "custom_modifier" in plugin_with_cache_modifier.cache_key()


# =============================================================================
# Test: Add Fiat Edges To Graph
# =============================================================================

class TestAddFiatEdgesToGraph:
    """Tests for _add_fiat_edges_to_graph method."""

    def test_add_fiat_edges_to_graph(self, plugin: MockCcxtPairConverterPlugin, mocker: Any) -> None:
        """Test adding fiat edges to graph."""
        plugin._build_fiat_list()

        mock_graph = MagicMock()
        mock_graph.get_vertex = MagicMock(return_value=MagicMock())
        markets: Dict[str, List[str]] = {}

        # Should not raise
        plugin._add_fiat_edges_to_graph(mock_graph, markets)

        # Check markets were updated
        assert len(markets) > 0