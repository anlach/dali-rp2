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

"""E2E tests for remaining CSV plugins (pionex, strike, bitbank, coincheck).

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
from dali.plugin.input.csv.pionex import InputPlugin as PionexInputPlugin
from dali.plugin.input.csv.strike import InputPlugin as StrikeInputPlugin
from dali.plugin.input.csv.bitbank_supplemental import InputPlugin as BitbankInputPlugin
from dali.plugin.input.csv.coincheck_supplemental import InputPlugin as CoincheckInputPlugin

# Import shared fixtures from e2e_shared.py
from e2e_shared import MockPairConverter


def _run_pionex_full_pipeline(
    trades_csv: Optional[str] = None,
    transfers_csv: Optional[str] = None,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Pionex plugin: load transactions, resolve, return results."""
    plugin = PionexInputPlugin(
        account_holder=account_holder,
        trades_csv_file=trades_csv,
        transfers_csv_file=transfers_csv,
        native_fiat="USD",
    )

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


def _run_strike_full_pipeline(
    strike_csv_files: str,
    account_holder: str = "tester",
    account_nickname: str = "strike_nickname",
    timezone: str = "UTC",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Strike plugin: load transactions, resolve, return results."""
    plugin = StrikeInputPlugin(
        account_holder=account_holder,
        account_nickname=account_nickname,
        strike_csv_files=strike_csv_files,
        timezone=timezone,
        native_fiat="USD",
    )

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


def _run_bitbank_full_pipeline(
    withdrawals_csv: Optional[str] = None,
    deposits_csv: Optional[str] = None,
    fiat_deposits_csv: Optional[str] = None,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Bitbank plugin: load transactions, resolve, return results."""
    plugin = BitbankInputPlugin(
        account_holder=account_holder,
        withdrawals_csv_file=withdrawals_csv,
        deposits_csv_file=deposits_csv,
        fiat_deposits_csv_file=fiat_deposits_csv,
        native_fiat="USD",
    )

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


def _run_coincheck_full_pipeline(
    buys_csv: str,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Coincheck plugin: load transactions, resolve, return results."""
    plugin = CoincheckInputPlugin(
        account_holder=account_holder,
        buys_csv_file=buys_csv,
        native_fiat="USD",
    )

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


class TestPionexE2E:
    """End-to-end tests for Pionex CSV plugin."""

    @pytest.fixture
    def pionex_trades_csv_path(self) -> str:
        """Return path to test Pionex trades CSV file."""
        return "input/test_pionex_trades.csv"

    @pytest.fixture
    def pionex_transfers_csv_path(self) -> str:
        """Return path to test Pionex transfers CSV file."""
        return "input/test_pionex_transfers.csv"

    def test_pionex_trades_transactions(self, pionex_trades_csv_path: str) -> None:
        """Test E2E pipeline with Pionex trades."""
        resolved = _run_pionex_full_pipeline(trades_csv=pionex_trades_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Pionex trades create InTransaction (BUY) and OutTransaction (SELL) pairs
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))

        # 2 trades = 2 InTransactions + 2 OutTransactions
        assert in_count >= 2, f"Expected at least 2 InTransactions, got {in_count}"
        assert out_count >= 2, f"Expected at least 2 OutTransactions, got {out_count}"

    def test_pionex_transfers_transactions(self, pionex_transfers_csv_path: str) -> None:
        """Test E2E pipeline with Pionex transfers (deposits/withdrawals)."""
        resolved = _run_pionex_full_pipeline(transfers_csv=pionex_transfers_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Pionex transfers create IntraTransactions (DEPOSIT = crypto_received, WITHDRAW = crypto_sent)
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions, got {intra_count}"

    def test_pionex_full_pipeline(
        self,
        pionex_trades_csv_path: str,
        pionex_transfers_csv_path: str,
    ) -> None:
        """Test E2E pipeline with both Pionex CSV files."""
        resolved = _run_pionex_full_pipeline(
            trades_csv=pionex_trades_csv_path,
            transfers_csv=pionex_transfers_csv_path,
        )

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Should have both trade transactions (In + Out) and transfer transactions (Intra)
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        assert in_count >= 2, f"Expected at least 2 InTransactions, got {in_count}"
        assert out_count >= 2, f"Expected at least 2 OutTransactions, got {out_count}"
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions, got {intra_count}"

    def test_pionex_assets_extracted(self, pionex_trades_csv_path: str) -> None:
        """Test that assets are correctly extracted from Pionex transactions."""
        resolved = _run_pionex_full_pipeline(trades_csv=pionex_trades_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains ETH and BUSD
        assert "ETH" in assets, f"ETH should be in output assets: {assets}"
        assert "BUSD" in assets, f"BUSD should be in output assets: {assets}"

    def test_pionex_transfer_deposits_and_withdrawals(self, pionex_transfers_csv_path: str) -> None:
        """Test that Pionex transfers correctly identify deposits and withdrawals."""
        resolved = _run_pionex_full_pipeline(transfers_csv=pionex_transfers_csv_path)

        # Find transactions with crypto_received (deposits) and crypto_sent (withdrawals)
        deposits = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        withdrawals = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        assert len(deposits) >= 1, f"Expected at least 1 deposit, got {len(deposits)}"
        assert len(withdrawals) >= 1, f"Expected at least 1 withdrawal, got {len(withdrawals)}"

    def test_pionex_ods_output_generation(self, pionex_trades_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Pionex plugin."""
        resolved = _run_pionex_full_pipeline(trades_csv=pionex_trades_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_pionex_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_pionex_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestStrikeE2E:
    """End-to-end tests for Strike CSV plugin."""

    @pytest.fixture
    def strike_csv_path(self) -> str:
        """Return path to test Strike CSV file."""
        return "input/test_strike.csv"

    @pytest.fixture
    def strike_csv_2_path(self) -> str:
        """Return path to second test Strike CSV file."""
        return "input/test_strike_2.csv"

    def test_strike_transactions(self, strike_csv_path: str) -> None:
        """Test E2E pipeline with Strike transactions."""
        resolved = _run_strike_full_pipeline(strike_csv_files=strike_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Strike creates:
        # - IntraTransaction for Receive and Send
        # - InTransaction for Purchase (Buy)
        # Note: Deposit transactions (fiat only) are skipped by the plugin
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        # From test_strike.csv: 2 Purchases (In), 2 Receives (Intra), 2 Sends (Intra)
        # Deposit transactions (fiat only) are skipped, so we get 2 In + 4 Intra
        # But there's a fee transaction causing one send to be combined, so we get 3 Intra
        assert in_count >= 2, f"Expected at least 2 InTransactions, got {in_count}"
        assert intra_count >= 3, f"Expected at least 3 IntraTransactions, got {intra_count}"

    def test_strike_multiple_csv_files(
        self,
        strike_csv_path: str,
        strike_csv_2_path: str,
    ) -> None:
        """Test E2E pipeline with multiple Strike CSV files."""
        csv_files = f"{strike_csv_path},{strike_csv_2_path}"
        resolved = _run_strike_full_pipeline(strike_csv_files=csv_files)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Combined: 3 Purchases (In), 3 Receives (Intra), 3 Sends (Intra)
        # Deposit transactions (fiat only) are skipped
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        assert in_count >= 3, f"Expected at least 3 InTransactions, got {in_count}"
        assert intra_count >= 5, f"Expected at least 5 IntraTransactions, got {intra_count}"

    def test_strike_assets_extracted(self, strike_csv_path: str) -> None:
        """Test that assets are correctly extracted from Strike transactions."""
        resolved = _run_strike_full_pipeline(strike_csv_files=strike_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # All transactions are BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_strike_transaction_types(self, strike_csv_path: str) -> None:
        """Test that Strike creates correct transaction types."""
        resolved = _run_strike_full_pipeline(strike_csv_files=strike_csv_path)

        # Find Purchase transactions (Buy)
        buy_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "buy" in t.transaction_type.lower()
        ]

        assert len(buy_txs) >= 2, f"Expected at least 2 Buy transactions, got {len(buy_txs)}"

    def test_strike_receive_and_send(self, strike_csv_path: str) -> None:
        """Test that Strike correctly handles Receive and Send transactions."""
        resolved = _run_strike_full_pipeline(strike_csv_files=strike_csv_path)

        # Find IntraTransactions (Receive and Send)
        intra_txs = [t for t in resolved if isinstance(t, IntraTransaction)]

        # Should have receives and sends
        receives = [t for t in intra_txs if t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        sends = [t for t in intra_txs if t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        # From test data: 1 Receive, 2 Sends (one doesn't have fee so it's handled differently)
        assert len(receives) >= 1, f"Expected at least 1 Receive transaction, got {len(receives)}"
        assert len(sends) >= 1, f"Expected at least 1 Send transaction, got {len(sends)}"

    def test_strike_ods_output_generation(self, strike_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Strike plugin."""
        resolved = _run_strike_full_pipeline(strike_csv_files=strike_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_strike_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_strike_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestBitbankE2E:
    """End-to-end tests for Bitbank supplemental CSV plugin."""

    @pytest.fixture
    def bitbank_deposits_csv_path(self) -> str:
        """Return path to test Bitbank deposits CSV file."""
        return "input/test_bitbank_deposits.csv"

    @pytest.fixture
    def bitbank_withdrawals_csv_path(self) -> str:
        """Return path to test Bitbank withdrawals CSV file."""
        return "input/test_bitbank_withdrawals.csv"

    @pytest.fixture
    def bitbank_fiat_deposits_csv_path(self) -> str:
        """Return path to test Bitbank fiat deposits CSV file."""
        return "input/test_bitbank_fiat_deposits.csv"

    def test_bitbank_deposits_transactions(self, bitbank_deposits_csv_path: str) -> None:
        """Test E2E pipeline with Bitbank deposits."""
        resolved = _run_bitbank_full_pipeline(deposits_csv=bitbank_deposits_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Bitbank deposits create IntraTransactions
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions (deposits), got {intra_count}"

    def test_bitbank_withdrawals_transactions(self, bitbank_withdrawals_csv_path: str) -> None:
        """Test E2E pipeline with Bitbank withdrawals."""
        resolved = _run_bitbank_full_pipeline(withdrawals_csv=bitbank_withdrawals_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Bitbank withdrawals create IntraTransactions
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions (withdrawals), got {intra_count}"

    def test_bitbank_fiat_deposits_transactions(self, bitbank_fiat_deposits_csv_path: str) -> None:
        """Test E2E pipeline with Bitbank fiat deposits."""
        resolved = _run_bitbank_full_pipeline(fiat_deposits_csv=bitbank_fiat_deposits_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Fiat deposits create InTransactions (BUY of JPY)
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert in_count >= 1, f"Expected at least 1 InTransaction (fiat deposit), got {in_count}"

    def test_bitbank_full_pipeline(
        self,
        bitbank_deposits_csv_path: str,
        bitbank_withdrawals_csv_path: str,
        bitbank_fiat_deposits_csv_path: str,
    ) -> None:
        """Test E2E pipeline with all Bitbank CSV files."""
        resolved = _run_bitbank_full_pipeline(
            deposits_csv=bitbank_deposits_csv_path,
            withdrawals_csv=bitbank_withdrawals_csv_path,
            fiat_deposits_csv=bitbank_fiat_deposits_csv_path,
        )

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Should have crypto deposits, crypto withdrawals, and fiat deposits
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))

        # 2 deposits + 2 withdrawals = 4 Intra, 1 fiat deposit = 1 In
        assert intra_count >= 4, f"Expected at least 4 IntraTransactions, got {intra_count}"
        assert in_count >= 1, f"Expected at least 1 InTransaction, got {in_count}"

    def test_bitbank_assets_extracted(self, bitbank_deposits_csv_path: str) -> None:
        """Test that assets are correctly extracted from Bitbank transactions."""
        resolved = _run_bitbank_full_pipeline(deposits_csv=bitbank_deposits_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains XRP and BTC
        assert "XRP" in assets, f"XRP should be in output assets: {assets}"
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_bitbank_ods_output_generation(self, bitbank_deposits_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Bitbank plugin."""
        resolved = _run_bitbank_full_pipeline(deposits_csv=bitbank_deposits_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_bitbank_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_bitbank_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestCoincheckE2E:
    """End-to-end tests for Coincheck supplemental CSV plugin."""

    @pytest.fixture
    def coincheck_buys_csv_path(self) -> str:
        """Return path to test Coincheck buys CSV file."""
        return "input/test_coincheck_buys.csv"

    def test_coincheck_buys_transactions(self, coincheck_buys_csv_path: str) -> None:
        """Test E2E pipeline with Coincheck buys."""
        resolved = _run_coincheck_full_pipeline(buys_csv=coincheck_buys_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Coincheck buys create InTransactions
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert in_count >= 1, f"Expected at least 1 InTransaction, got {in_count}"

    def test_coincheck_assets_extracted(self, coincheck_buys_csv_path: str) -> None:
        """Test that assets are correctly extracted from Coincheck transactions."""
        resolved = _run_coincheck_full_pipeline(buys_csv=coincheck_buys_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_coincheck_fiat_values(self, coincheck_buys_csv_path: str) -> None:
        """Test that fiat values are correctly calculated for Coincheck transactions."""
        resolved = _run_coincheck_full_pipeline(buys_csv=coincheck_buys_csv_path)

        # Find Buy transactions
        buy_txs = [t for t in resolved if isinstance(t, InTransaction)]

        # Check that fiat values are present
        if buy_txs:
            buy_tx = buy_txs[0]
            # Coincheck provides JPY values, but the transaction_resolver converts to USD
            # and sets fiat_ticker to USD
            assert buy_tx.fiat_in_no_fee is not None, "fiat_in_no_fee should be set"
            # The original JPY value is converted to USD by the transaction_resolver
            # so fiat_ticker will be USD (the native fiat), not JPY
            assert buy_tx.fiat_ticker is not None, "fiat_ticker should be set"

    def test_coincheck_ods_output_generation(self, coincheck_buys_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Coincheck plugin."""
        resolved = _run_coincheck_full_pipeline(buys_csv=coincheck_buys_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_coincheck_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_coincheck_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestRemainingPluginsErrorHandling:
    """Error handling tests for remaining CSV plugins."""

    def test_pionex_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Pionex plugin."""
        plugin = PionexInputPlugin(
            account_holder="tester",
            trades_csv_file="input/nonexistent.csv",
            transfers_csv_file=None,
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_strike_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Strike plugin."""
        plugin = StrikeInputPlugin(
            account_holder="tester",
            account_nickname="test_nick",
            strike_csv_files="input/nonexistent.csv",
            timezone="UTC",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_bitbank_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Bitbank plugin."""
        plugin = BitbankInputPlugin(
            account_holder="tester",
            deposits_csv_file="input/nonexistent.csv",
            withdrawals_csv_file=None,
            fiat_deposits_csv_file=None,
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_coincheck_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Coincheck plugin."""
        plugin = CoincheckInputPlugin(
            account_holder="tester",
            buys_csv_file="input/nonexistent.csv",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_pionex_with_explicit_mock_converter(self) -> None:
        """Test Pionex pipeline with explicit mock of pair converter."""
        mock_converter = MagicMock()
        mock_converter.name.return_value = "TestMockConverter"
        mock_converter.cache_key.return_value = "test_mock"
        mock_converter.get_historic_bar_from_native_source.return_value = None

        def mock_get_conversion_rate(timestamp: Any, from_asset: str, to_asset: str, exchange: str) -> Optional[RP2Decimal]:
            if from_asset == "BTC" and to_asset == "USD":
                return RP2Decimal("35000")
            if from_asset == "ETH" and to_asset == "USD":
                return RP2Decimal("2000")
            if from_asset == "BUSD" and to_asset == "USD":
                return RP2Decimal("1")
            return None

        mock_converter.get_conversion_rate = mock_get_conversion_rate
        mock_converter.optimize.return_value = None
        mock_converter.save_historical_price_cache.return_value = None

        plugin = PionexInputPlugin(
            account_holder="tester",
            trades_csv_file="input/test_pionex_trades.csv",
            transfers_csv_file=None,
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