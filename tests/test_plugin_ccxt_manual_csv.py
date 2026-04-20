# Copyright 2024 Neal Chambers
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

import os
import pytest
from datetime import datetime, timezone

from rp2.rp2_decimal import RP2Decimal
from dali.plugin.pair_converter.ccxt_manual_csv import PairConverterPlugin, _DEFAULT_CSV_DIRECTORY, _DEFAULT_TIMEZONE


# Test data directory - use a temporary directory for tests
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "test_data", "manual_csv")


class TestManualCsvPairConverter:
    """Tests for Manual CSV Pair Converter Plugin."""

    @pytest.fixture
    def plugin(self):
        """Create a plugin instance for testing."""
        return PairConverterPlugin(
            historical_price_type="close",
            csv_directory=TEST_DATA_DIR,
            timezone="UTC",
        )

    @pytest.fixture
    def plugin_with_timezone(self):
        """Create a plugin instance with US/Eastern timezone."""
        return PairConverterPlugin(
            historical_price_type="close",
            csv_directory=TEST_DATA_DIR,
            timezone="America/New_York",
        )

    def test_name(self, plugin):
        """Test that plugin name is correct."""
        assert plugin.name() == "Manual CSV"

    def test_default_values(self):
        """Test default CSV directory and timezone."""
        plugin = PairConverterPlugin(historical_price_type="close")
        assert plugin._csv_directory == _DEFAULT_CSV_DIRECTORY
        assert plugin._timezone_name == _DEFAULT_TIMEZONE

    def test_custom_values(self):
        """Test custom CSV directory and timezone."""
        custom_dir = ".dali_cache/custom/"
        custom_tz = "America/Los_Angeles"
        plugin = PairConverterPlugin(
            historical_price_type="close",
            csv_directory=custom_dir,
            timezone=custom_tz,
        )
        assert plugin._csv_directory == custom_dir
        assert plugin._timezone_name == custom_tz

    def test_parse_timezone_utc(self):
        """Test UTC timezone parsing."""
        plugin = PairConverterPlugin(historical_price_type="close", timezone="UTC")
        assert plugin._timezone == timezone.utc

    def test_parse_timezone_gmt(self):
        """Test GMT timezone parsing (alias for UTC)."""
        plugin = PairConverterPlugin(historical_price_type="close", timezone="GMT")
        assert plugin._timezone == timezone.utc

    def test_get_historical_bar_btc_usd(self, plugin):
        """Test getting BTC/USD price from CSV."""
        # CSV has 2025-01-01 00:00:00 UTC
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = plugin._get_fiat_exchange_rate(timestamp, "BTC", "USD")

        assert result is not None
        assert result.open == RP2Decimal("95000.00")
        assert result.high == RP2Decimal("96000.00")
        assert result.low == RP2Decimal("94000.00")
        assert result.close == RP2Decimal("95500.00")
        assert result.volume == RP2Decimal("12345.67")

    def test_get_historical_bar_usd_btc_inverse(self, plugin):
        """Test getting USD/BTC price (inverse of BTC/USD)."""
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = plugin._get_fiat_exchange_rate(timestamp, "USD", "BTC")

        assert result is not None
        # Inverse of 95500 (the close price, not open) = 1/95500 ≈ 0.00001047
        assert float(result.close) == pytest.approx(1 / 95500.0, rel=1e-6)

    def test_get_historical_bar_missing_pair(self, plugin):
        """Test missing pair returns None."""
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = plugin._get_fiat_exchange_rate(timestamp, "ETH", "USD")

        assert result is None

    def test_get_historical_bar_missing_file(self, plugin):
        """Test missing CSV file returns None."""
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = plugin._get_fiat_exchange_rate(timestamp, "XYZ", "ABC")

        assert result is None

    def test_cache_behavior(self, plugin):
        """Test that results are cached."""
        timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # First call - should load from CSV
        result1 = plugin._get_fiat_exchange_rate(timestamp, "BTC", "USD")
        assert result1 is not None

        # Second call - should come from cache
        result2 = plugin._get_fiat_exchange_rate(timestamp, "BTC", "USD")
        assert result2 is not None
        assert result1 == result2

    def test_timezone_handling(self, plugin_with_timezone):
        """Test timezone handling for CSV timestamps."""
        # CSV file has 00:00:00 in America/New_York (EST)
        # That's 05:00:00 UTC
        # Query at 05:00 UTC should match
        timestamp_utc = datetime(2025, 1, 1, 5, 0, 0, tzinfo=timezone.utc)
        result = plugin_with_timezone._get_fiat_exchange_rate(timestamp_utc, "BTC", "USD")

        assert result is not None
        assert result.close == RP2Decimal("95500.00")

    def test_different_date(self, plugin):
        """Test getting price for a different date."""
        # 2025-01-02 in the CSV
        timestamp = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        result = plugin._get_fiat_exchange_rate(timestamp, "BTC", "USD")

        assert result is not None
        assert result.close == RP2Decimal("96000.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])