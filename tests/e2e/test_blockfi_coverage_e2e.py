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

"""E2E tests for BlockFi CSV plugin to improve coverage from 57% to 80%+.

These tests verify all transaction types supported by the BlockFi plugin:
- Interest Payment
- Referral Bonus
- Bonus Payment
- Crypto Transfer
- ACH Withdrawal
- Withdrawal (with and without fee)
- ACH Deposit
- Trade (skipped in transaction CSV, handled in trade_report)
- BIA Withdraw (skipped)
- parse_trade_report method
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


# Mock prices for testing
MOCK_BTC_USD_PRICE = "35000"
MOCK_ETH_USD_PRICE = "2000"
MOCK_USDC_USD_PRICE = "1"


class MockPairConverter:
    """Mock pair converter that returns fixed prices for testing."""

    def __init__(
        self,
        btc_price: str = MOCK_BTC_USD_PRICE,
        eth_price: str = MOCK_ETH_USD_PRICE,
        usdc_price: str = MOCK_USDC_USD_PRICE,
    ):
        self._btc_price = btc_price
        self._eth_price = eth_price
        self._usdc_price = usdc_price
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
        if from_asset == "USDC" and to_asset == "USD":
            return RP2Decimal(self._usdc_price)
        if from_asset == "USD" and to_asset == "USDC":
            return RP2Decimal(str(1 / float(self._usdc_price)))
        # Handle USDT conversions
        if from_asset == "USDT" and to_asset == "USD":
            return RP2Decimal("1")
        if from_asset == "USD" and to_asset == "USDT":
            return RP2Decimal("1")
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


class TestBlockfiCoverageE2E:
    """End-to-end tests for BlockFi CSV plugin to improve coverage."""

    def test_blockfi_crypto_transfer(self) -> None:
        """Test Crypto Transfer transaction type creates IntraTransaction."""
        csv_path = "input/test_blockfi_crypto_transfer.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

        # Crypto Transfer creates IntraTransactions
        assert len(resolved) > 0, "Should have resolved transactions"

        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 2, f"Expected at least 2 IntraTransactions (Crypto Transfer), got {intra_count}"

        # Check assets include both BTC and ETH
        assets = set(t.asset for t in resolved if t.asset)
        assert "BTC" in assets, f"BTC should be in assets: {assets}"
        assert "ETH" in assets, f"ETH should be in assets: {assets}"

    def test_blockfi_withdrawal_fee(self) -> None:
        """Test Withdrawal Fee followed by Withdrawal creates proper IntraTransaction."""
        csv_path = "input/test_blockfi_withdrawal_fee.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

        # Withdrawal with fee should create an IntraTransaction
        assert len(resolved) > 0, "Should have resolved transactions"

        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"

    def test_blockfi_trade_csv(self) -> None:
        """Test trade CSV parsing via parse_trade_report method."""
        transaction_csv = "input/test_blockfi_transactions.csv"
        trade_csv = "input/test_blockfi_trades.csv"
        resolved = _run_blockfi_full_pipeline(
            transaction_csv=transaction_csv,
            trade_csv=trade_csv,
        )

        # Should have both regular transactions and trade transactions
        assert len(resolved) > 0, "Should have resolved transactions"

        # Trades create both OutTransaction (sell) and InTransaction (buy)
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))

        # Original transactions: 3 In (Interest, Referral Bonus, ACH Deposit), 1 Out (ACH Withdrawal)
        # Trade CSV: Trade 12345 (BTC -> ETH): 1 Out + 1 In
        # Trade CSV: Trade 12346 (ETH -> USDC): 1 Out + 1 In
        # Total: 5 In, 3 Out
        assert in_count >= 5, f"Expected at least 5 InTransactions, got {in_count}"
        assert out_count >= 3, f"Expected at least 3 OutTransactions, got {out_count}"

        # Check assets include all from trades
        assets = set(t.asset for t in resolved if t.asset)
        assert "BTC" in assets, f"BTC should be in assets: {assets}"
        assert "ETH" in assets, f"ETH should be in assets: {assets}"
        assert "USDC" in assets, f"USDC should be in assets: {assets}"

    def test_blockfi_skipped_transactions(self) -> None:
        """Test Trade and BIA Withdraw are properly skipped."""
        csv_path = "input/test_blockfi_skipped.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

        # Trade and BIA Withdraw are skipped, but Interest Payment is still processed
        # So we should have 1 InTransaction for Interest Payment
        assert len(resolved) >= 1, "Should have at least Interest Payment transaction"

        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert in_count >= 1, f"Expected at least 1 InTransaction (Interest Payment), got {in_count}"

    def test_blockfi_bonus_payment(self) -> None:
        """Test Bonus Payment transaction type (similar to Referral Bonus)."""
        csv_path = "input/test_blockfi_bonus.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

        # Bonus Payment creates InTransaction with transaction_type = Income
        assert len(resolved) > 0, "Should have resolved transactions"

        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        assert in_count >= 1, f"Expected at least 1 InTransaction, got {in_count}"

        # Check it's an Income transaction
        income_txs = [
            t for t in resolved
            if isinstance(t, InTransaction)
            and t.transaction_type
            and "income" in t.transaction_type.lower()
        ]
        assert len(income_txs) >= 1, f"Expected at least 1 Income transaction, got {len(income_txs)}"

    def test_blockfi_full_pipeline(self) -> None:
        """Test full pipeline with multiple transaction types."""
        # Use existing test data
        transaction_csv = "input/test_blockfi_transactions.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=transaction_csv)

        assert len(resolved) > 0, "Should have resolved transactions"

        # Check all transaction types
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        # From test_blockfi_transactions.csv:
        # - Interest Payment (InTransaction)
        # - Referral Bonus (InTransaction)
        # - ACH Deposit (InTransaction)
        # - ACH Withdrawal (OutTransaction)
        assert in_count >= 3, f"Expected at least 3 InTransactions, got {in_count}"
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"
        assert intra_count == 0, f"Expected 0 IntraTransactions, got {intra_count}"

    def test_blockfi_ods_output_generation(self) -> None:
        """Test that ODS output file is generated correctly for BlockFi plugin."""
        csv_path = "input/test_blockfi_transactions.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

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

    def test_blockfi_assets_extracted(self) -> None:
        """Test that assets are correctly extracted from BlockFi transactions."""
        csv_path = "input/test_blockfi_transactions.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

        assets = set(t.asset for t in resolved if t.asset)
        assert "BTC" in assets, f"BTC should be in output assets: {assets}"

    def test_blockfi_transaction_types(self) -> None:
        """Test that BlockFi creates correct transaction types."""
        csv_path = "input/test_blockfi_transactions.csv"
        resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

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

    def test_blockfi_withdrawal_fee_error(self) -> None:
        """Test error when withdrawal fee is not followed by withdrawal."""
        # Create CSV where withdrawal fee is NOT followed by withdrawal
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "bad_withdrawal_fee.csv")
            with open(csv_path, "w") as f:
                f.write("currency,amount,type,timestamp\n")
                f.write("BTC,0.001,Withdrawal Fee,2022-11-01 10:00:00\n")
                f.write("BTC,0.1,Interest Payment,2022-11-01 11:00:00\n")

            plugin = BlockfiInputPlugin(
                account_holder="tester",
                transaction_csv_file=csv_path,
                trade_csv_file=None,
                native_fiat="USD",
            )

            # Should raise error because withdrawal fee is not followed by withdrawal
            from rp2.rp2_error import RP2RuntimeError
            with pytest.raises(RP2RuntimeError, match="withdrawal fee.*not followed by withdrawal"):
                plugin.load(US())


class TestBlockfiE2EMocking:
    """Additional E2E tests with explicit mocking for BlockFi plugin."""

    def test_blockfi_with_explicit_mock_converter(self) -> None:
        """Test BlockFi pipeline with explicit mock of pair converter."""
        mock_converter = MagicMock()
        mock_converter.name.return_value = "TestMockConverter"
        mock_converter.cache_key.return_value = "test_mock"
        mock_converter.get_historic_bar_from_native_source.return_value = None

        def mock_get_conversion_rate(timestamp: Any, from_asset: str, to_asset: str, exchange: str) -> Optional[RP2Decimal]:
            if from_asset == "BTC" and to_asset == "USD":
                return RP2Decimal("35000")
            if from_asset == "ETH" and to_asset == "USD":
                return RP2Decimal("2000")
            if from_asset == "USDC" and to_asset == "USD":
                return RP2Decimal("1")
            return None

        mock_converter.get_conversion_rate = mock_get_conversion_rate
        mock_converter.optimize.return_value = None
        mock_converter.save_historical_price_cache.return_value = None

        csv_path = "input/test_blockfi_transactions.csv"
        plugin = BlockfiInputPlugin(
            account_holder="tester",
            transaction_csv_file=csv_path,
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

    def test_blockfi_error_handling_missing_csv(self) -> None:
        """Test error handling when CSV file is missing."""
        plugin = BlockfiInputPlugin(
            account_holder="tester",
            transaction_csv_file="input/nonexistent_blockfi.csv",
            trade_csv_file=None,
            native_fiat="USD",
        )

        with pytest.raises(FileNotFoundError):
            plugin.load(US())

    def test_blockfi_mixed_transactions(self) -> None:
        """Test BlockFi with mixed transaction types."""
        # Create CSV with multiple transaction types
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "mixed_transactions.csv")
            with open(csv_path, "w") as f:
                f.write("currency,amount,type,timestamp\n")
                f.write("BTC,0.05,Interest Payment,2022-06-15 10:30:00\n")
                f.write("BTC,0.01,Referral Bonus,2022-07-01 14:20:00\n")
                f.write("BTC,0.02,Bonus Payment,2022-07-15 10:00:00\n")
                f.write("BTC,0.5,Crypto Transfer,2022-08-01 12:00:00\n")
                f.write("BTC,0.1,Ach Deposit,2022-08-10 09:00:00\n")
                f.write("BTC,0.05,Ach Withdrawal,2022-09-05 16:45:00\n")

            resolved = _run_blockfi_full_pipeline(transaction_csv=csv_path)

            assert len(resolved) > 0, "Should have resolved transactions"

            # Count each type
            in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
            out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
            intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

            # Interest Payment (In) + Referral Bonus (In) + Bonus Payment (In) + ACH Deposit (In) = 4 In
            # ACH Withdrawal (Out) = 1 Out
            # Crypto Transfer (Intra) = 1 Intra
            assert in_count >= 4, f"Expected at least 4 InTransactions, got {in_count}"
            assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"
            assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"