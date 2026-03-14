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

import logging
from datetime import datetime, timedelta, timezone
from os import path
from typing import List, Optional

from rp2.rp2_decimal import ZERO, RP2Decimal

from dali.abstract_ccxt_pair_converter_plugin import (
    DEFAULT_FIAT_LIST,
    AbstractCcxtPairConverterPlugin,
)
from dali.abstract_pair_converter_plugin import AssetPairAndTimestamp
from dali.historical_bar import HistoricalBar

_FOREX_CSV_DOC_URL: str = "https://github.com/eprbell/dali-rp2/blob/main/docs/configuration_file.md"
_MANUAL_CSV_EXCHANGE: str = "Manual CSV"

# Default values
_DEFAULT_CSV_DIRECTORY: str = ".dali_cache/manual_prices/"
_DEFAULT_TIMEZONE: str = "UTC"


class PairConverterPlugin(AbstractCcxtPairConverterPlugin):
    """Manual CSV Pair Converter Plugin for Dali-RP2.

    This plugin allows users to provide manual price data via CSV files as a fallback
    when automated price sources (like Kraken, Coinbase) fail or don't have data.

    CSV File Format:
        Time,Open,High,Low,Close,Volume
        2025-01-15 10:00:00,100.50,101.25,99.75,100.90,1500.0

    File Naming Convention:
        {FROM_ASSET}_{TO_ASSET}.csv (e.g., BTC_USD.csv, ETH_BTC.csv)

    Configuration (INI file):
        [MANUAL_CSV]
        historical_price_type = close
        csv_directory = .dali_cache/manual_prices/
        timezone = America/New_York
    """

    def __init__(
        self,
        historical_price_type: str,
        default_exchange: Optional[str] = None,
        fiat_priority: Optional[str] = None,
        exchange_locked: Optional[bool] = None,
        untradeable_assets: Optional[str] = None,
        aliases: Optional[str] = None,
        csv_directory: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> None:
        # Ensure directory has trailing slash
        self._csv_directory: str = (csv_directory if csv_directory else _DEFAULT_CSV_DIRECTORY).rstrip("/") + "/"
        self._timezone_name: str = timezone if timezone else _DEFAULT_TIMEZONE
        self._timezone: timezone = self._parse_timezone(self._timezone_name)

        # Use cache_modifier to differentiate from other CSV plugins
        cache_modifier = "manual_csv"

        super().__init__(
            historical_price_type=historical_price_type,
            exchange_locked=exchange_locked,
            untradeable_assets=untradeable_assets,
            aliases=aliases,
            cache_modifier=cache_modifier,
        )

    def name(self) -> str:
        return "Manual CSV"

    def _parse_timezone(self, tz_name: str) -> timezone:
        """Parse timezone string into timezone object.

        Supports:
        - UTC/GMT (aliases)
        - IANA timezone names (America/New_York, Europe/London, etc.)
        - Offset format (+05:30, -08:00)

        Args:
            tz_name: Timezone name or offset string

        Returns:
            timezone object

        Raises:
            ValueError: If timezone format is invalid
        """
        tz_name = tz_name.strip()

        # Handle common aliases
        if tz_name.upper() in ("UTC", "GMT", "Z"):
            return timezone.utc

        # Try to import zoneinfo (Python 3.9+)
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(tz_name)
        except ImportError:
            # Fall back to pytz for older Python versions
            pass

        # Try pytz if available
        try:
            import pytz

            return pytz.timezone(tz_name)
        except ImportError:
            pass
        except pytz.exceptions.UnknownTimeZoneError:
            pass

        # Try to parse offset format (+05:30, -08:00)
        if tz_name.startswith(("+", "-")) and ":" in tz_name:
            try:
                sign = 1 if tz_name.startswith("+") else -1
                hours, minutes = map(int, tz_name[1:].split(":"))
                total_seconds = sign * (hours * 3600 + minutes * 60)
                return timezone(timedelta(seconds=total_seconds))
            except (ValueError, IndexError):
                pass

        # Default to UTC if all else fails
        logging.getLogger(__name__).warning(
            "Unknown timezone '%s', defaulting to UTC. "
            "Please install zoneinfo (Python 3.9+) or pytz for full timezone support.",
            tz_name
        )
        return timezone.utc

    def _get_fiat_exchange_rate(self, timestamp: datetime, from_asset: str, to_asset: str) -> Optional[HistoricalBar]:
        """Look up exchange rate from manual CSV files.

        Args:
            timestamp: The timestamp to look up
            from_asset: The base asset (e.g., BTC)
            to_asset: The quote asset (e.g., USD)

        Returns:
            HistoricalBar if found, None otherwise
        """
        key: AssetPairAndTimestamp = AssetPairAndTimestamp(timestamp, from_asset, to_asset, _MANUAL_CSV_EXCHANGE)
        historical_bar: Optional[HistoricalBar] = self._get_bar_from_cache(key)

        if historical_bar is not None:
            self._logger.debug("Retrieved cache for %s/%s->%s for %s", timestamp, from_asset, to_asset, _MANUAL_CSV_EXCHANGE)
            return historical_bar

        # Try both forward and reverse file names
        csv_file: str = f"{self._csv_directory}{key.from_asset}_{key.to_asset}.csv"
        file_exists = path.exists(csv_file)
        reverse_pair: bool = False

        if not file_exists:
            csv_file = f"{self._csv_directory}{key.to_asset}_{key.from_asset}.csv"
            reverse_pair = path.exists(csv_file)

            if not reverse_pair:
                self._logger.info("No CSV file found for %s for %s/%s", key.timestamp, key.from_asset, key.to_asset)
                self._logger.info("Please save a CSV file with pricing information named %s_%s.csv to %s ",
                    key.from_asset, key.to_asset, self._csv_directory)
                self._logger.info("For more details, check the documentation. %s", _FOREX_CSV_DOC_URL)
                return None

        try:
            with open(csv_file, encoding="utf-8") as file:
                lines: List[str] = file.readlines()

                # Find the header line to determine column positions
                header_line = ""
                header_parts: List[str] = []
                for line in lines:
                    if line.strip().lower().startswith("time"):
                        header_line = line.strip()
                        header_parts = [h.strip().lower() for h in line.split(",")]
                        break

                if not header_parts:
                    self._logger.warning("CSV file %s has no valid header row", csv_file)
                    return None

                # Find column indices
                try:
                    time_idx = header_parts.index("time")
                    open_idx = header_parts.index("open")
                    high_idx = header_parts.index("high")
                    low_idx = header_parts.index("low")
                    close_idx = header_parts.index("close")
                    volume_idx = header_parts.index("volume")
                except ValueError as e:
                    self._logger.warning("CSV file %s is missing required columns: %s", csv_file, e)
                    return None

                # Parse the timestamp in the configured timezone
                # Convert the input timestamp to the configured timezone for comparison
                ts_with_tz = timestamp.replace(tzinfo=self._timezone)
                ts_date_str = ts_with_tz.strftime("%Y-%m-%d %H:%M:%S")

                for line in lines:
                    if line.startswith("Time") or line.startswith("time"):
                        continue

                    parts: List[str] = line.strip().split(",")
                    if len(parts) < 6:
                        continue

                    try:
                        # Parse the CSV timestamp
                        csv_time_str = parts[time_idx].strip()
                        csv_datetime = datetime.strptime(csv_time_str, "%Y-%m-%d %H:%M:%S")

                        # Make CSV time timezone-aware and convert to UTC for comparison
                        # Handle both zoneinfo.ZoneInfo (has localize) and datetime.timezone (doesn't)
                        if csv_datetime.tzinfo is None:
                            if hasattr(self._timezone, 'localize'):
                                csv_datetime = self._timezone.localize(csv_datetime)
                            else:
                                # For datetime.timezone, just attach it directly
                                csv_datetime = csv_datetime.replace(tzinfo=self._timezone)
                        csv_datetime_utc = csv_datetime.astimezone(timezone.utc)
                        csv_date_str = csv_datetime_utc.strftime("%Y-%m-%d %H:%M:%S")

                        # Compare timestamps
                        if csv_date_str == ts_date_str:
                            # Found matching timestamp
                            result = HistoricalBar(
                                duration=timedelta(days=1),
                                timestamp=ts_with_tz,
                                open=RP2Decimal(parts[open_idx]),
                                high=RP2Decimal(parts[high_idx]),
                                low=RP2Decimal(parts[low_idx]),
                                close=RP2Decimal(parts[close_idx]),
                                volume=RP2Decimal(parts[volume_idx]),
                            )
                            self._add_bar_to_cache(key, result)

                            # Also cache the reverse pair
                            reverse_key: AssetPairAndTimestamp = AssetPairAndTimestamp(
                                key.timestamp, key.to_asset, key.from_asset, _MANUAL_CSV_EXCHANGE
                            )
                            reverse_result = HistoricalBar(
                                duration=timedelta(days=1),
                                timestamp=ts_with_tz,
                                open=RP2Decimal("1") / result.open,
                                high=RP2Decimal("1") / result.high,
                                low=RP2Decimal("1") / result.low,
                                close=RP2Decimal("1") / result.close,
                                volume=ZERO,
                            )
                            self._add_bar_to_cache(reverse_key, reverse_result)

                            if reverse_pair:
                                return reverse_result
                            return result

                    except (ValueError, IndexError) as e:
                        self._logger.debug("Error parsing line in CSV: %s - %s", line.strip(), e)
                        continue

        except FileNotFoundError:
            self._logger.debug("File not found: %s", csv_file)
        except IOError as e:
            self._logger.warning("Error reading CSV file %s: %s", csv_file, e)

        # No historical bar found
        return None

    def _build_fiat_list(self) -> None:
        """Build the list of fiat assets this plugin can handle.

        Since this is a manual CSV plugin, we accept all assets - the user
        provides the CSV files for any pairs they need.
        """
        self._fiat_list = DEFAULT_FIAT_LIST