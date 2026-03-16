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

"""E2E tests for uncovered CSV plugins (blockfi, electrum, ledger, nexo, trezor, trezor_old, trezor_v2).

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
from dali.plugin.input.csv.blockfi import InputPlugin as BlockfiInputPlugin
from dali.plugin.input.csv.electrum import InputPlugin as ElectrumInputPlugin
from dali.plugin.input.csv.ledger import InputPlugin as LedgerInputPlugin
from dali.plugin.input.csv.nexo import InputPlugin as NexoInputPlugin
from dali.plugin.input.csv.trezor import InputPlugin as TrezorInputPlugin
from dali.plugin.input.csv.trezor_old import InputPlugin as TrezorOldInputPlugin
from dali.plugin.input.csv.trezor_v2 import InputPlugin as TrezorV2InputPlugin


# Mock prices for testing
MOCK_BTC_USD_PRICE = "35000"
MOCK_ETH_USD_PRICE = "2000"
MOCK_FTM_USD_PRICE = "0.5"


class MockPairConverter:
    """Mock pair converter that returns fixed prices for testing."""

    def __init__(
        self,
        btc_price: str = MOCK_BTC_USD_PRICE,
        eth_price: str = MOCK_ETH_USD_PRICE,
        ftm_price: str = MOCK_FTM_USD_PRICE,
    ):
        self._btc_price = btc_price
        self._eth_price = eth_price
        self._ftm_price = ftm_price
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
        # Return mock prices for common conversions
        if from_asset == "BTC" and to_asset == "USD":
            return RP2Decimal(self._btc_price)
        if from_asset == "USD" and to_asset == "BTC":
            return RP2Decimal(str(1 / float(self._btc_price)))
        if from_asset == "ETH" and to_asset == "USD":
            return RP2Decimal(self._eth_price)
        if from_asset == "USD" and to_asset == "ETH":
            return RP2Decimal(str(1 / float(self._eth_price)))
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
        # No-op for mock
        pass


def _run_blockfi_full_pipeline(
    transaction_csv: Optional[str] = None,
    trade_csv: Optional[str] = None,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for BlockFi plugin: load transactions, resolve, return results."""
    plugin = BlockfiInputPlugin(
        account_holder=account_holder,
        transaction_csv_file=transaction_csv,
        trade_csv_file=trade_csv,
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


def _run_electrum_full_pipeline(
    csv_file: str,
    account_holder: str = "tester",
    account_nickname: str = "test_nick",
    timezone: str = "UTC",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Electrum plugin: load transactions, resolve, return results."""
    plugin = ElectrumInputPlugin(
        account_holder=account_holder,
        account_nickname=account_nickname,
        csv_file=csv_file,
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


def _run_ledger_full_pipeline(
    csv_file: str,
    account_holder: str = "tester",
    account_nickname: str = "test_nick",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Ledger plugin: load transactions, resolve, return results."""
    plugin = LedgerInputPlugin(
        account_holder=account_holder,
        account_nickname=account_nickname,
        csv_file=csv_file,
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


def _run_nexo_full_pipeline(
    transaction_csv: str,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Nexo plugin: load transactions, resolve, return results."""
    plugin = NexoInputPlugin(
        account_holder=account_holder,
        transaction_csv_file=transaction_csv,
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


def _run_trezor_full_pipeline(
    csv_file: str,
    account_holder: str = "tester",
    account_nickname: str = "test_nick",
    currency: str = "BTC",
    timezone: str = "UTC",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Trezor plugin: load transactions, resolve, return results."""
    plugin = TrezorInputPlugin(
        account_holder=account_holder,
        account_nickname=account_nickname,
        currency=currency,
        timezone=timezone,
        csv_file=csv_file,
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


def _run_trezor_old_full_pipeline(
    csv_file: str,
    account_holder: str = "tester",
    account_nickname: str = "test_nick",
    currency: str = "BTC",
    timezone: str = "UTC",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Trezor Old plugin: load transactions, resolve, return results."""
    plugin = TrezorOldInputPlugin(
        account_holder=account_holder,
        account_nickname=account_nickname,
        currency=currency,
        timezone=timezone,
        csv_file=csv_file,
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


def _run_trezor_v2_full_pipeline(
    csv_file: str,
    account_holder: str = "tester",
    account_nickname: str = "test_nick",
    currency: str = "BTC",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for Trezor V2 plugin: load transactions, resolve, return results."""
    plugin = TrezorV2InputPlugin(
        account_holder=account_holder,
        account_nickname=account_nickname,
        currency=currency,
        csv_file=csv_file,
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


class TestBlockfiE2E:
    """End-to-end tests for BlockFi CSV plugin."""

    @pytest.fixture
    def blockfi_transactions_csv_path(self) -> str:
        """Return path to test BlockFi transactions CSV file."""
        return "input/test_blockfi_transactions.csv"

    def test_blockfi_transactions(self, blockfi_transactions_csv_path: str) -> None:
        """Test E2E pipeline with BlockFi transactions."""
        resolved = _run_blockfi_full_pipeline(transaction_csv=blockfi_transactions_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # BlockFi creates:
        # - InTransaction: Interest Payment (Buy), Referral Bonus (Income), ACH Deposit (Buy)
        # - OutTransaction: ACH Withdrawal (Sell)
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))

        # From test data: 3 In (Interest Payment, Referral Bonus, ACH Deposit), 1 Out (ACH Withdrawal)
        assert in_count >= 3, f"Expected at least 3 InTransactions, got {in_count}"
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"

    def test_blockfi_assets_extracted(self, blockfi_transactions_csv_path: str) -> None:
        """Test that assets are correctly extracted from BlockFi transactions."""
        resolved = _run_blockfi_full_pipeline(transaction_csv=blockfi_transactions_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_blockfi_transaction_types(self, blockfi_transactions_csv_path: str) -> None:
        """Test that BlockFi creates correct transaction types."""
        resolved = _run_blockfi_full_pipeline(transaction_csv=blockfi_transactions_csv_path)

        # Find Interest transactions
        interest_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "interest" in t.transaction_type.lower()
        ]
        assert len(interest_txs) >= 1, f"Expected at least 1 Interest transaction, got {len(interest_txs)}"

        # Find Buy transactions (ACH Deposit)
        buy_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "buy" in t.transaction_type.lower()
        ]
        assert len(buy_txs) >= 1, f"Expected at least 1 Buy transaction, got {len(buy_txs)}"

    def test_blockfi_ods_output_generation(self, blockfi_transactions_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for BlockFi plugin."""
        resolved = _run_blockfi_full_pipeline(transaction_csv=blockfi_transactions_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_blockfi_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_blockfi_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestElectrumE2E:
    """End-to-end tests for Electrum (Yoroi) CSV plugin."""

    @pytest.fixture
    def electrum_csv_path(self) -> str:
        """Return path to test Electrum CSV file."""
        return "input/test_electrum.csv"

    def test_electrum_transactions(self, electrum_csv_path: str) -> None:
        """Test E2E pipeline with Electrum transactions."""
        resolved = _run_electrum_full_pipeline(csv_file=electrum_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Electrum creates IntraTransactions (IN for deposits, OUT for withdrawals)
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions, got {intra_count}"

    def test_electrum_assets_extracted(self, electrum_csv_path: str) -> None:
        """Test that assets are correctly extracted from Electrum transactions."""
        resolved = _run_electrum_full_pipeline(csv_file=electrum_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_electrum_deposits_and_withdrawals(self, electrum_csv_path: str) -> None:
        """Test that Electrum correctly identifies deposits and withdrawals."""
        resolved = _run_electrum_full_pipeline(csv_file=electrum_csv_path)

        # Find transactions with crypto_received (deposits) and crypto_sent (withdrawals)
        deposits = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        withdrawals = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        assert len(deposits) >= 1, f"Expected at least 1 deposit, got {len(deposits)}"
        assert len(withdrawals) >= 1, f"Expected at least 1 withdrawal, got {len(withdrawals)}"

    def test_electrum_ods_output_generation(self, electrum_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Electrum plugin."""
        resolved = _run_electrum_full_pipeline(csv_file=electrum_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_electrum_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_electrum_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestLedgerE2E:
    """End-to-end tests for Ledger CSV plugin."""

    @pytest.fixture
    def ledger_csv_path(self) -> str:
        """Return path to test Ledger CSV file."""
        return "input/test_ledger.csv"

    def test_ledger_transactions(self, ledger_csv_path: str) -> None:
        """Test E2E pipeline with Ledger transactions."""
        resolved = _run_ledger_full_pipeline(csv_file=ledger_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Ledger creates IntraTransactions (IN for receive, OUT for send)
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 3, f"Expected at least 3 IntraTransactions, got {intra_count}"

    def test_ledger_assets_extracted(self, ledger_csv_path: str) -> None:
        """Test that assets are correctly extracted from Ledger transactions."""
        resolved = _run_ledger_full_pipeline(csv_file=ledger_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC, ETH, FTM (FANTOM)
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"
        assert "ETH" in assets, f"ETH should be in output assets: {assets}"
        assert "FTM" in assets, f"FTM should be in output assets: {assets}"

    def test_ledger_receives_and_sends(self, ledger_csv_path: str) -> None:
        """Test that Ledger correctly identifies receives and sends."""
        resolved = _run_ledger_full_pipeline(csv_file=ledger_csv_path)

        # Find transactions with crypto_received and crypto_sent
        receives = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        sends = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        assert len(receives) >= 1, f"Expected at least 1 receive transaction, got {len(receives)}"
        assert len(sends) >= 1, f"Expected at least 1 send transaction, got {len(sends)}"

    def test_ledger_ods_output_generation(self, ledger_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Ledger plugin."""
        resolved = _run_ledger_full_pipeline(csv_file=ledger_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_ledger_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_ledger_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestNexoE2E:
    """End-to-end tests for Nexo CSV plugin."""

    @pytest.fixture
    def nexo_csv_path(self) -> str:
        """Return path to test Nexo CSV file."""
        return "input/test_nexo.csv"

    def test_nexo_transactions(self, nexo_csv_path: str) -> None:
        """Test E2E pipeline with Nexo transactions."""
        resolved = _run_nexo_full_pipeline(transaction_csv=nexo_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Nexo creates:
        # - InTransaction: Interest, FixedTermInterest
        # - IntraTransaction: Deposit
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        # From test data: 2 In (Interest, FixedTermInterest), 1 Intra (Deposit)
        assert in_count >= 2, f"Expected at least 2 InTransactions, got {in_count}"
        assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"

    def test_nexo_assets_extracted(self, nexo_csv_path: str) -> None:
        """Test that assets are correctly extracted from Nexo transactions."""
        resolved = _run_nexo_full_pipeline(transaction_csv=nexo_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC and ETH
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"
        assert "ETH" in assets, f"ETH should be in output assets: {assets}"

    def test_nexo_transaction_types(self, nexo_csv_path: str) -> None:
        """Test that Nexo creates correct transaction types."""
        resolved = _run_nexo_full_pipeline(transaction_csv=nexo_csv_path)

        # Find Interest transactions
        interest_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "interest" in t.transaction_type.lower()
        ]
        assert len(interest_txs) >= 2, f"Expected at least 2 Interest transactions, got {len(interest_txs)}"

    def test_nexo_deposits(self, nexo_csv_path: str) -> None:
        """Test that Nexo correctly handles deposit transactions."""
        resolved = _run_nexo_full_pipeline(transaction_csv=nexo_csv_path)

        # Find IntraTransactions (Deposits)
        deposits = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]

        assert len(deposits) >= 1, f"Expected at least 1 deposit, got {len(deposits)}"

    def test_nexo_ods_output_generation(self, nexo_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Nexo plugin."""
        resolved = _run_nexo_full_pipeline(transaction_csv=nexo_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_nexo_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_nexo_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestTrezorE2E:
    """End-to-end tests for Trezor CSV plugin (original version)."""

    @pytest.fixture
    def trezor_csv_path(self) -> str:
        """Return path to test Trezor CSV file."""
        return "input/test_trezor_v1.csv"

    def test_trezor_transactions(self, trezor_csv_path: str) -> None:
        """Test E2E pipeline with Trezor transactions."""
        resolved = _run_trezor_full_pipeline(csv_file=trezor_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Trezor creates IntraTransactions (RECV for receive, SENT for send)
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions, got {intra_count}"

    def test_trezor_assets_extracted(self, trezor_csv_path: str) -> None:
        """Test that assets are correctly extracted from Trezor transactions."""
        resolved = _run_trezor_full_pipeline(csv_file=trezor_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_trezor_receives_and_sends(self, trezor_csv_path: str) -> None:
        """Test that Trezor correctly identifies receives and sends."""
        resolved = _run_trezor_full_pipeline(csv_file=trezor_csv_path)

        # Find transactions with crypto_received and crypto_sent
        receives = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        sends = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        assert len(receives) >= 1, f"Expected at least 1 receive transaction, got {len(receives)}"
        assert len(sends) >= 1, f"Expected at least 1 send transaction, got {len(sends)}"

    def test_trezor_ods_output_generation(self, trezor_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Trezor plugin."""
        resolved = _run_trezor_full_pipeline(csv_file=trezor_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_trezor_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_trezor_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestTrezorOldE2E:
    """End-to-end tests for Trezor Old CSV plugin (Trezor Web interface)."""

    @pytest.fixture
    def trezor_old_csv_path(self) -> str:
        """Return path to test Trezor Old CSV file."""
        return "input/test_trezor_old.csv"

    def test_trezor_old_transactions(self, trezor_old_csv_path: str) -> None:
        """Test E2E pipeline with Trezor Old transactions."""
        resolved = _run_trezor_old_full_pipeline(csv_file=trezor_old_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Trezor Old creates IntraTransactions (IN for receive, OUT for send)
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions, got {intra_count}"

    def test_trezor_old_assets_extracted(self, trezor_old_csv_path: str) -> None:
        """Test that assets are correctly extracted from Trezor Old transactions."""
        resolved = _run_trezor_old_full_pipeline(csv_file=trezor_old_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_trezor_old_receives_and_sends(self, trezor_old_csv_path: str) -> None:
        """Test that Trezor Old correctly identifies receives and sends."""
        resolved = _run_trezor_old_full_pipeline(csv_file=trezor_old_csv_path)

        # Find transactions with crypto_received and crypto_sent
        receives = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        sends = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        assert len(receives) >= 1, f"Expected at least 1 receive transaction, got {len(receives)}"
        assert len(sends) >= 1, f"Expected at least 1 send transaction, got {len(sends)}"

    def test_trezor_old_ods_output_generation(self, trezor_old_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Trezor Old plugin."""
        resolved = _run_trezor_old_full_pipeline(csv_file=trezor_old_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_trezor_old_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_trezor_old_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestTrezorV2E2E:
    """End-to-end tests for Trezor V2 CSV plugin (newer Trezor Suite format)."""

    @pytest.fixture
    def trezor_v2_csv_path(self) -> str:
        """Return path to test Trezor V2 CSV file."""
        return "input/test_trezor_v2.csv"

    def test_trezor_v2_transactions(self, trezor_v2_csv_path: str) -> None:
        """Test E2E pipeline with Trezor V2 transactions."""
        resolved = _run_trezor_v2_full_pipeline(csv_file=trezor_v2_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Trezor V2 creates IntraTransactions (RECV for receive, SENT for send)
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions, got {intra_count}"

    def test_trezor_v2_assets_extracted(self, trezor_v2_csv_path: str) -> None:
        """Test that assets are correctly extracted from Trezor V2 transactions."""
        resolved = _run_trezor_v2_full_pipeline(csv_file=trezor_v2_csv_path)

        # Extract unique assets
        assets = set(t.asset for t in resolved if t.asset)

        # Test data contains BTC
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_trezor_v2_receives_and_sends(self, trezor_v2_csv_path: str) -> None:
        """Test that Trezor V2 correctly identifies receives and sends."""
        resolved = _run_trezor_v2_full_pipeline(csv_file=trezor_v2_csv_path)

        # Find transactions with crypto_received and crypto_sent
        receives = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value]
        sends = [t for t in resolved if isinstance(t, IntraTransaction) and t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value]

        assert len(receives) >= 1, f"Expected at least 1 receive transaction, got {len(receives)}"
        assert len(sends) >= 1, f"Expected at least 1 send transaction, got {len(sends)}"

    def test_trezor_v2_ods_output_generation(self, trezor_v2_csv_path: str) -> None:
        """Test that ODS output file is generated correctly for Trezor V2 plugin."""
        resolved = _run_trezor_v2_full_pipeline(csv_file=trezor_v2_csv_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            dali_configuration: Dict[str, Any] = {
                Keyword.NATIVE_FIAT.value: "USD",
            }

            generate_input_file(
                output_dir_path=tmpdir,
                output_file_prefix="test_trezor_v2_",
                output_file_name="crypto_data.ods",
                transactions=resolved,
                global_configuration=dali_configuration,
            )

            ods_path = os.path.join(tmpdir, "test_trezor_v2_crypto_data.ods")
            assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
            assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"


class TestUncoveredPluginsErrorHandling:
    """Error handling tests for uncovered CSV plugins."""

    def test_blockfi_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for BlockFi plugin."""
        plugin = BlockfiInputPlugin(
            account_holder="tester",
            transaction_csv_file="input/nonexistent.csv",
            trade_csv_file=None,
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_electrum_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Electrum plugin."""
        plugin = ElectrumInputPlugin(
            account_holder="tester",
            account_nickname="test_nick",
            csv_file="input/nonexistent.csv",
            timezone="UTC",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_ledger_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Ledger plugin."""
        plugin = LedgerInputPlugin(
            account_holder="tester",
            account_nickname="test_nick",
            csv_file="input/nonexistent.csv",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_nexo_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Nexo plugin."""
        plugin = NexoInputPlugin(
            account_holder="tester",
            transaction_csv_file="input/nonexistent.csv",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_trezor_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Trezor plugin."""
        plugin = TrezorInputPlugin(
            account_holder="tester",
            account_nickname="test_nick",
            currency="BTC",
            timezone="UTC",
            csv_file="input/nonexistent.csv",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_trezor_old_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Trezor Old plugin."""
        plugin = TrezorOldInputPlugin(
            account_holder="tester",
            account_nickname="test_nick",
            currency="BTC",
            timezone="UTC",
            csv_file="input/nonexistent.csv",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_trezor_v2_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing for Trezor V2 plugin."""
        plugin = TrezorV2InputPlugin(
            account_holder="tester",
            account_nickname="test_nick",
            currency="BTC",
            csv_file="input/nonexistent.csv",
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_blockfi_with_explicit_mock_converter(self) -> None:
        """Test BlockFi pipeline with explicit mock of pair converter."""
        mock_converter = MagicMock()
        mock_converter.name.return_value = "TestMockConverter"
        mock_converter.cache_key.return_value = "test_mock"
        mock_converter.get_historic_bar_from_native_source.return_value = None

        def mock_get_conversion_rate(timestamp: Any, from_asset: str, to_asset: str, exchange: str) -> Optional[RP2Decimal]:
            if from_asset == "BTC" and to_asset == "USD":
                return RP2Decimal("35000")
            return None

        mock_converter.get_conversion_rate = mock_get_conversion_rate
        mock_converter.optimize.return_value = None
        mock_converter.save_historical_price_cache.return_value = None

        plugin = BlockfiInputPlugin(
            account_holder="tester",
            transaction_csv_file="input/test_blockfi_transactions.csv",
            trade_csv_file=None,
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