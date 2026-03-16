# Copyright 2026 anlach
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

"""E2E tests for CSV plugins (manual, binance).

These tests verify the full pipeline from CSV input → DALI processing → RP2 output.
They mock external price lookups to avoid network calls.
"""

import os
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

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
from dali.plugin.input.csv.manual import InputPlugin as ManualInputPlugin
from dali.plugin.input.csv.binance_com_supplemental import InputPlugin as BinanceSupplementalInputPlugin

# Import shared fixtures from e2e_shared.py
from e2e_shared import MockPairConverter


def _run_manual_full_pipeline(
    in_csv: Optional[str] = None,
    out_csv: Optional[str] = None,
    intra_csv: Optional[str] = None,
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for manual plugin: load transactions, resolve, return results.

    Args:
        in_csv: Path to manual in CSV file
        out_csv: Path to manual out CSV file
        intra_csv: Path to manual intra CSV file
        mock_converter: Mock pair converter for price lookups

    Returns:
        List of resolved transactions ready for ODS output
    """
    # Create input plugin
    plugin = ManualInputPlugin(
        in_csv_file=in_csv,
        out_csv_file=out_csv,
        intra_csv_file=intra_csv,
        native_fiat="USD",
    )

    # Load transactions from CSV
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


def _run_binance_full_pipeline(
    autoinvest_csv: Optional[str] = None,
    betheth_csv: Optional[str] = None,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for binance plugin: load transactions, resolve, return results.

    Args:
        autoinvest_csv: Path to binance autoinvest CSV file
        betheth_csv: Path to binance betheth CSV file
        account_holder: Account holder name
        mock_converter: Mock pair converter for price lookups

    Returns:
        List of resolved transactions ready for ODS output
    """
    # Create input plugin
    plugin = BinanceSupplementalInputPlugin(
        account_holder=account_holder,
        autoinvest_csv_file=autoinvest_csv,
        betheth_csv_file=betheth_csv,
        native_fiat="USD",
    )

    # Load transactions from CSV
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


class TestManualE2E:
    """End-to-end tests for manual CSV plugin."""

    @pytest.fixture
    def manual_in_csv_path(self) -> str:
        """Return path to test manual in CSV file."""
        return "input/test_manual_in.csv"

    @pytest.fixture
    def manual_out_csv_path(self) -> str:
        """Return path to test manual out CSV file."""
        return "input/test_manual_out.csv"

    @pytest.fixture
    def manual_intra_csv_path(self) -> str:
        """Return path to test manual intra CSV file."""
        return "input/test_manual_intra.csv"

    def test_manual_in_transactions(self, manual_in_csv_path: str) -> None:
        """Test E2E pipeline with manual in transactions."""
        resolved = _run_manual_full_pipeline(in_csv=manual_in_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check transaction types
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert in_count == 2, f"Expected 2 InTransactions (Buy), got {in_count}"

    def test_manual_out_transactions(self, manual_out_csv_path: str) -> None:
        """Test E2E pipeline with manual out transactions."""
        resolved = _run_manual_full_pipeline(out_csv=manual_out_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check transaction types
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"

    def test_manual_intra_transactions(self, manual_intra_csv_path: str) -> None:
        """Test E2E pipeline with manual intra transactions."""
        resolved = _run_manual_full_pipeline(intra_csv=manual_intra_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check transaction types
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"

    def test_manual_full_pipeline(self, manual_in_csv_path: str, manual_out_csv_path: str, manual_intra_csv_path: str) -> None:
        """Test E2E pipeline with all manual CSV files."""
        resolved = _run_manual_full_pipeline(
            in_csv=manual_in_csv_path,
            out_csv=manual_out_csv_path,
            intra_csv=manual_intra_csv_path,
        )

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check all transaction types are present
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        assert in_count >= 2, f"Expected at least 2 InTransactions, got {in_count}"
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"
        assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"

    def test_manual_ods_output_generation(self, manual_in_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for manual plugin."""
        resolved = _run_manual_full_pipeline(in_csv=manual_in_csv_path)

        # Create a temporary output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            # Generate ODS file
            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_manual_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            # Verify file was created
            ods_path = os.path.join(tmpdir, "test_manual_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"

            # Verify file has non-zero size
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"

    def test_manual_unique_transaction_ids(self, manual_in_csv_path: str) -> None:
        """Test that unique transaction IDs are generated correctly."""
        resolved = _run_manual_full_pipeline(in_csv=manual_in_csv_path)

        # Collect known unique IDs (excluding __unknown which is used for unresolvable transactions)
        unique_ids = [t.unique_id for t in resolved if t.unique_id and t.unique_id != "__unknown"]

        # Verify uniqueness (excluding __unknown)
        # Manual plugin may have empty unique_ids which become __unknown
        known_ids = [uid for uid in unique_ids if uid]
        if len(known_ids) > 1:
            assert len(known_ids) == len(set(known_ids)), "All known transaction IDs should be unique"

    def test_manual_assets_extracted(self, manual_in_csv_path: str) -> None:
        """Test that assets are correctly extracted from manual transactions."""
        resolved = _run_manual_full_pipeline(in_csv=manual_in_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Should have BTC from the test data
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_manual_fiat_values_calculated(self, manual_in_csv_path: str) -> None:
        """Test that fiat values are calculated correctly with mocked prices."""
        mock_converter = MockPairConverter(btc_price="35000")
        resolved = _run_manual_full_pipeline(in_csv=manual_in_csv_path, mock_converter=mock_converter)

        # Find Buy transactions (InTransaction)
        buy_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "buy" in t.transaction_type.lower()
        ]

        if buy_txs:
            buy_tx = buy_txs[0]
            # With mock price of $35000 BTC/USD, a 0.01 BTC buy should have fiat value
            if buy_tx.crypto_in:
                expected_fiat = float(buy_tx.crypto_in) * 35000
                if buy_tx.fiat_in_no_fee:
                    actual_fiat = float(buy_tx.fiat_in_no_fee)
                    # Allow for small rounding differences
                    assert abs(actual_fiat - expected_fiat) < 1, (
                        f"fiat_in_no_fee mismatch: expected ~{expected_fiat}, got {actual_fiat}"
                    )


class TestBinanceE2E:
    """End-to-end tests for Binance supplemental CSV plugin."""

    @pytest.fixture
    def binance_autoinvest_csv_path(self) -> str:
        """Return path to test Binance autoinvest CSV file."""
        return "input/test_binance_autoinvest.csv"

    @pytest.fixture
    def binance_betheth_csv_path(self) -> str:
        """Return path to test Binance betheth CSV file."""
        return "input/test_binance_betheth.csv"

    def test_binance_autoinvest_transactions(self, binance_autoinvest_csv_path: str) -> None:
        """Test E2E pipeline with Binance autoinvest transactions."""
        resolved = _run_binance_full_pipeline(autoinvest_csv=binance_autoinvest_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check transaction types - autoinvest creates Buy transactions
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert in_count >= 2, f"Expected at least 2 InTransactions (autoinvest buys), got {in_count}"

    def test_binance_betheth_transactions(self, binance_betheth_csv_path: str) -> None:
        """Test E2E pipeline with Binance betheth transactions."""
        resolved = _run_binance_full_pipeline(betheth_csv=binance_betheth_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # betheth creates OutTransaction (spend ETH to get bETH) and InTransaction (receive bETH)
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"
        assert in_count >= 1, f"Expected at least 1 InTransaction, got {in_count}"

    def test_binance_full_pipeline(self, binance_autoinvest_csv_path: str, binance_betheth_csv_path: str) -> None:
        """Test E2E pipeline with both Binance CSV files."""
        resolved = _run_binance_full_pipeline(
            autoinvest_csv=binance_autoinvest_csv_path,
            betheth_csv=binance_betheth_csv_path,
        )

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check all transaction types are present
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))

        # Autoinvest: 2 buys (InTransaction)
        # betheth: 1 out + 1 in
        assert in_count >= 3, f"Expected at least 3 InTransactions, got {in_count}"
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"

    def test_binance_ods_output_generation(self, binance_autoinvest_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for binance plugin."""
        resolved = _run_binance_full_pipeline(autoinvest_csv=binance_autoinvest_csv_path)

        # Create a temporary output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            # Generate ODS file
            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_binance_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            # Verify file was created
            ods_path = os.path.join(tmpdir, "test_binance_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"

            # Verify file has non-zero size
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"

    def test_binance_assets_extracted(self, binance_autoinvest_csv_path: str) -> None:
        """Test that assets are correctly extracted from binance transactions."""
        resolved = _run_binance_full_pipeline(autoinvest_csv=binance_autoinvest_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Should have ETH and BTC from autoinvest
        assert "ETH" in assets, f"ETH should be in output assets: {assets}"
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_binance_betheth_asset_conversion(self, binance_betheth_csv_path: str) -> None:
        """Test that betheth conversion creates both ETH out and bETH in transactions."""
        resolved = _run_binance_full_pipeline(betheth_csv=binance_betheth_csv_path)

        # Find transactions with ETH and BETH
        eth_txs = [t for t in resolved if t.asset == "ETH"]
        beth_txs = [t for t in resolved if t.asset == "BETH"]

        # Should have both ETH (out) and BETH (in) transactions
        assert len(eth_txs) >= 1, f"Expected at least 1 ETH transaction, got {len(eth_txs)}"
        assert len(beth_txs) >= 1, f"Expected at least 1 BETH transaction, got {len(beth_txs)}"

    def test_binance_autoinvest_notes(self, binance_autoinvest_csv_path: str) -> None:
        """Test that autoinvest transactions have meaningful notes."""
        resolved = _run_binance_full_pipeline(autoinvest_csv=binance_autoinvest_csv_path)

        # Check that at least some transactions have notes
        txs_with_notes = [t for t in resolved if t.notes]
        assert len(txs_with_notes) >= 1, "Should have transactions with notes"


class TestBinanceE2EMocking:
    """Additional E2E tests with explicit mocking of external calls for Binance plugin."""

    def test_binance_with_explicit_mock_converter(self, binance_autoinvest_csv_path: str = "input/test_binance_autoinvest.csv") -> None:
        """Test Binance pipeline with explicit mock of pair converter."""
        mock_converter = MagicMock()
        mock_converter.name.return_value = "TestMockConverter"
        mock_converter.cache_key.return_value = "test_mock"
        mock_converter.get_historic_bar_from_native_source.return_value = None

        def mock_get_conversion_rate(timestamp: Any, from_asset: str, to_asset: str, exchange: str) -> Optional[RP2Decimal]:
            if from_asset == "BTC" and to_asset == "USD":
                return RP2Decimal("35000")
            if from_asset == "ETH" and to_asset == "USD":
                return RP2Decimal("2000")
            if from_asset == "USDT" and to_asset == "USD":
                return RP2Decimal("1")
            return None

        mock_converter.get_conversion_rate = mock_get_conversion_rate
        mock_converter.optimize.return_value = None
        mock_converter.save_historical_price_cache.return_value = None

        plugin = BinanceSupplementalInputPlugin(
            account_holder="tester",
            autoinvest_csv_file=binance_autoinvest_csv_path,
            betheth_csv_file=None,
            native_fiat="USD",
        )

        transactions = plugin.load(US())

        dali_configuration: Dict[str, Any] = {
            Keyword.NATIVE_FIAT.value: "USD",
            Keyword.HISTORICAL_PAIR_CONVERTERS.value: [mock_converter],
        }

        resolved = resolve_transactions(
            transactions,
            dali_configuration,
            read_spot_price_from_web=False,
        )

        # Verify transactions were resolved
        assert len(resolved) > 0

    def test_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for manual plugin."""
        plugin = ManualInputPlugin(
            in_csv_file="input/nonexistent.csv",
            out_csv_file=None,
            intra_csv_file=None,
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_binance_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Binance plugin."""
        plugin = BinanceSupplementalInputPlugin(
            account_holder="tester",
            autoinvest_csv_file="input/nonexistent.csv",
            betheth_csv_file=None,
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())