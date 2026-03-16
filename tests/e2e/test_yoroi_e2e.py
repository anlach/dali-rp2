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

"""E2E tests for Yoroi plugin with Minswap integration.

These tests verify the full pipeline from CSV input → DALI processing → RP2 output.
They mock external price lookups to avoid network calls.
"""

import os
import tempfile
from typing import Any, Callable, Dict, List, Optional
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
from dali.plugin.input.csv.yoroi import InputPlugin

# Import shared fixtures from e2e_shared.py
from e2e_shared import MockPairConverter


# Mock price for ADA/USD - used in testing
MOCK_ADA_USD_PRICE = "0.35"


def _run_full_pipeline(
    yoroi_csv: str,
    minswap_csv: Optional[str] = None,
    mock_price: str = MOCK_ADA_USD_PRICE,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline: load transactions, resolve, return results.

    Args:
        yoroi_csv: Path to Yoroi CSV file
        minswap_csv: Optional path to Minswap CSV file
        mock_price: Mock price for ADA/USD conversions

    Returns:
        List of resolved transactions ready for ODS output
    """
    # Create input plugin
    plugin = InputPlugin(
        account_holder="tester",
        account_nickname="yoroi_wallet",
        csv_file=yoroi_csv,
        timezone="UTC",
        native_fiat="USD",
        minswap_csv=minswap_csv,
    )

    # Load transactions from CSV
    transactions = plugin.load(US())

    # Set up mock configuration with mocked pair converter
    mock_converter = MockPairConverter(price=mock_price)
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


class TestYoroiE2E:
    """End-to-end tests for Yoroi plugin with Minswap integration."""

    @pytest.fixture
    def yoroi_csv_path(self) -> str:
        """Return path to test Yoroi CSV file."""
        return "input/test_yoroi.csv"

    @pytest.fixture
    def minswap_csv_path(self) -> str:
        """Return path to test Minswap CSV file."""
        return "input/test_minswap.csv"

    def test_full_pipeline_yoroi_only(self, yoroi_csv_path: str) -> None:
        """Test E2E pipeline with Yoroi CSV only (no Minswap)."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=None)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check we have various transaction types
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        # Should have staking rewards (InTransaction) and deposits/withdrawals (IntraTransaction)
        assert in_count >= 3, f"Expected at least 3 InTransactions (staking rewards), got {in_count}"
        assert intra_count >= 10, f"Expected at least 10 IntraTransactions, got {intra_count}"

    def test_full_pipeline_with_minswap(self, yoroi_csv_path: str, minswap_csv_path: str) -> None:
        """Test E2E pipeline with Yoroi + Minswap integration."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=minswap_csv_path)

        # Verify transactions were loaded
        assert len(resolved) > 0, "Should have resolved transactions"

        # With Minswap integration, we should have additional swap transactions
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        # Minswap adds:
        # - 4 swaps (8 transactions: 4 sells + 4 buys)
        # - 1 LP deposit (2 transactions)
        # - 1 LP removal (2 transactions)
        # Total from Minswap: ~12 additional transactions

        # We should have more OutTransactions due to swaps
        assert out_count >= 4, f"Expected at least 4 OutTransactions (swap sells), got {out_count}"

        # Should have staking rewards + token buys from swaps
        assert in_count >= 7, f"Expected at least 7 InTransactions, got {in_count}"

    def test_unique_transaction_ids_generated(self, yoroi_csv_path: str, minswap_csv_path: str) -> None:
        """Test that unique transaction IDs are generated correctly in output."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=minswap_csv_path)

        # Collect known unique IDs (excluding __unknown which is used for unresolvable transactions)
        unique_ids = [t.unique_id for t in resolved if t.unique_id and t.unique_id != "__unknown"]

        # Verify uniqueness (excluding __unknown)
        assert len(unique_ids) == len(set(unique_ids)), "All known transaction IDs should be unique"

        # Verify that at least some transactions have valid IDs
        assert len(unique_ids) > 0, "Should have some transactions with known unique IDs"

    def test_ods_output_generation(self, yoroi_csv_path: str) -> None:
        """Test that ODS output file is generated correctly."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=None)

        # Create a temporary output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            # Generate ODS file
            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            # Verify file was created
            ods_path = os.path.join(tmpdir, "test_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"

            # Verify file has non-zero size
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"

    def test_ods_output_contains_expected_assets(self, yoroi_csv_path: str, minswap_csv_path: str) -> None:
        """Test that ODS output contains expected assets."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=minswap_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Should have ADA as primary asset
        assert "ADA" in assets, f"ADA should be in output assets: {assets}"

    def test_fiat_values_calculated(self, yoroi_csv_path: str) -> None:
        """Test that fiat values are calculated correctly with mocked prices."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=None, mock_price="0.35")

        # Find InTransactions (staking rewards)
        staking_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "staking" in t.transaction_type.lower()
        ]

        if staking_txs:
            staking_tx = staking_txs[0]
            # With mock price of $0.35, a 0.5 ADA reward should have fiat values
            if staking_tx.crypto_in:
                expected_fiat = float(staking_tx.crypto_in) * 0.35
                if staking_tx.fiat_in_no_fee:
                    actual_fiat = float(staking_tx.fiat_in_no_fee)
                    # Allow for small rounding differences
                    assert abs(actual_fiat - expected_fiat) < 0.01, (
                        f"fiat_in_no_fee mismatch: expected ~{expected_fiat}, got {actual_fiat}"
                    )

    def test_minswap_swap_transactions(self, yoroi_csv_path: str, minswap_csv_path: str) -> None:
        """Test that Minswap swap transactions are properly integrated."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=minswap_csv_path)

        # Find swap-related transactions
        swap_out_txs = [
            t for t in resolved
            if isinstance(t, OutTransaction)
            and t.notes
            and "swap" in t.notes.lower()
        ]

        swap_in_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.notes
            and "swap" in t.notes.lower()
        ]

        # Should have swap transactions
        assert len(swap_out_txs) >= 4, f"Expected at least 4 swap OutTransactions, got {len(swap_out_txs)}"
        assert len(swap_in_txs) >= 4, f"Expected at least 4 swap InTransactions, got {len(swap_in_txs)}"

    def test_lp_transactions(self, yoroi_csv_path: str, minswap_csv_path: str) -> None:
        """Test that LP removal transactions are handled (LP deposit is tracked internally for cost basis)."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=minswap_csv_path)

        # Find LP removal transactions (the deposit is stored internally for cost basis tracking)
        lp_removal_txs = [
            t for t in resolved
            if t.notes
            and "LP" in t.notes
            and ("removal" in t.notes.lower() or "Zap Out" in t.notes)
        ]

        # Should have LP removal transactions
        assert len(lp_removal_txs) >= 1, f"Expected at least 1 LP removal transactions, got {len(lp_removal_txs)}"

        # Additionally verify that Minswap operations are present
        minswap_txs = [
            t for t in resolved
            if t.notes and "Minswap" in t.notes
        ]
        # Should have: 4 swaps (8 txs) + 1 LP removal (2 txs) = 10 Minswap transactions
        assert len(minswap_txs) >= 10, f"Expected at least 10 Minswap transactions, got {len(minswap_txs)}"

    def test_transaction_timestamps_preserved(self, yoroi_csv_path: str) -> None:
        """Test that transaction timestamps are preserved through the pipeline."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=None)

        # Verify all transactions have timestamps
        for tx in resolved:
            assert tx.timestamp is not None, "All transactions should have timestamps"
            assert len(tx.timestamp) > 0, "Timestamps should not be empty"

    def test_multiple_assets_from_swaps(self, yoroi_csv_path: str, minswap_csv_path: str) -> None:
        """Test that swap transactions include multiple token assets from Minswap."""
        resolved = _run_full_pipeline(yoroi_csv_path, minswap_csv=minswap_csv_path)

        # Extract unique assets from InTransactions (token buys from swaps)
        in_assets = set(
            t.asset for t in resolved
            if isinstance(t, InTransaction) and t.asset
        )

        # Should have ADA plus at least one other token from swaps (MIN, SNEK, WMTX)
        assert "ADA" in in_assets, "Should have ADA from staking/swap buys"
        assert len(in_assets) >= 2, f"Should have multiple assets from swaps, got: {in_assets}"


class TestYoroiE2EMocking:
    """Additional E2E tests with explicit mocking of external calls."""

    def test_with_explicit_mock_converter(self, yoroi_csv_path: str = "input/test_yoroi.csv") -> None:
        """Test pipeline with explicit mock of pair converter."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file=yoroi_csv_path,
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",  # Use minswap to get transactions with IDs
        )

        transactions = plugin.load(US())

        # Create mock converter with proper implementation
        mock_converter = MagicMock()
        mock_converter.name.return_value = "TestMockConverter"
        mock_converter.cache_key.return_value = "test_mock"
        mock_converter.get_historic_bar_from_native_source.return_value = None

        def mock_get_conversion_rate(timestamp: Any, from_asset: str, to_asset: str, exchange: str) -> Optional[RP2Decimal]:
            if from_asset == "ADA" and to_asset == "USD":
                return RP2Decimal("0.35")
            return None

        mock_converter.get_conversion_rate = mock_get_conversion_rate
        mock_converter.optimize.return_value = None
        mock_converter.save_historical_price_cache.return_value = None

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
        """Test error handling when CSV file is missing."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/nonexistent.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv=None,
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())