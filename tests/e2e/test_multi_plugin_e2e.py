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

"""E2E tests for multi-plugin cross-exchange transaction resolution.

These tests verify the full pipeline from multiple CSV plugins → DALI processing →
RP2 output, specifically testing the transaction resolver's ability to match
transactions across exchanges and handle various scenarios like partial transactions,
cross-exchange transfers, and multiple asset types.
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
from dali.plugin.input.csv.pionex import InputPlugin as PionexInputPlugin


# Mock prices for testing
MOCK_BTC_USD_PRICE = "35000"
MOCK_ETH_USD_PRICE = "2000"
MOCK_ADA_USD_PRICE = "0.35"
MOCK_USDT_USD_PRICE = "1"


class MockPairConverter:
    """Mock pair converter that returns fixed prices for testing."""

    def __init__(
        self,
        btc_price: str = MOCK_BTC_USD_PRICE,
        eth_price: str = MOCK_ETH_USD_PRICE,
        ada_price: str = MOCK_ADA_USD_PRICE,
        usdt_price: str = MOCK_USDT_USD_PRICE,
    ):
        self._btc_price = btc_price
        self._eth_price = eth_price
        self._ada_price = ada_price
        self._usdt_price = usdt_price
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
        if from_asset == "ADA" and to_asset == "USD":
            return RP2Decimal(self._ada_price)
        if from_asset == "USD" and to_asset == "ADA":
            return RP2Decimal(str(1 / float(self._ada_price)))
        if from_asset == "USDT" and to_asset == "USD":
            return RP2Decimal(self._usdt_price)
        if from_asset == "USD" and to_asset == "USDT":
            return RP2Decimal(str(1 / float(self._usdt_price)))
        return None

    def optimize(self, manifest: Any) -> None:
        pass

    def save_historical_price_cache(self) -> None:
        # No-op for mock
        pass


def _run_manual_full_pipeline(
    in_csv: Optional[str] = None,
    out_csv: Optional[str] = None,
    intra_csv: Optional[str] = None,
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for manual plugin: load transactions, resolve, return results."""
    plugin = ManualInputPlugin(
        in_csv_file=in_csv,
        out_csv_file=out_csv,
        intra_csv_file=intra_csv,
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


def _run_binance_full_pipeline(
    autoinvest_csv: Optional[str] = None,
    betheth_csv: Optional[str] = None,
    account_holder: str = "tester",
    mock_converter: Optional[MockPairConverter] = None,
) -> List[AbstractTransaction]:
    """Run the full DALI pipeline for binance plugin: load transactions, resolve, return results."""
    plugin = BinanceSupplementalInputPlugin(
        account_holder=account_holder,
        autoinvest_csv_file=autoinvest_csv,
        betheth_csv_file=betheth_csv,
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


class TestCrossExchangeTransfer:
    """Tests for cross-exchange transaction resolution."""

    @pytest.fixture
    def intra_csv_path(self) -> str:
        """Return path to test manual intra CSV file."""
        return "input/test_manual_intra.csv"

    def test_intra_transaction_resolution(self, intra_csv_path: str) -> None:
        """Test that intra transactions resolve correctly."""
        resolved = _run_manual_full_pipeline(intra_csv=intra_csv_path)

        # Verify transactions were loaded and resolved
        assert len(resolved) > 0, "Should have resolved transactions"

        # Check transaction types
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
        assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"

    def test_cross_exchange_transfer_with_matching_ids(self) -> None:
        """Test cross-exchange transfer where transactions have matching unique IDs."""
        # Create a temporary intra CSV with matching send/receive transactions
        # INTRA CSV format: 11 fields (Unique ID, Timestamp, Asset, From Exchange, From Holder, To Exchange, To Holder, Spot Price, Crypto Sent, Crypto Received, Notes)
        intra_csv_content = """Unique ID,Timestamp,Asset,From Exchange,From Holder,To Exchange,To Holder,Spot Price,Crypto Sent,Crypto Received,Notes
abc123def456,2022-01-14 10:35:10 +0000,BTC,Binance,User1,,,35000,0.5,,Sent 0.5 BTC to Coinbase,
abc123def456,2022-01-14 10:35:15 +0000,BTC,,,Binance,User2,35000,,0.5,Received 0.5 BTC from Binance,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(intra_csv_content)
            intra_csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(intra_csv=intra_csv_path)

            # The resolver should merge these two transactions into one
            assert len(resolved) > 0, "Should have resolved transactions"

            # Find the resolved transaction
            resolved_intra = [t for t in resolved if isinstance(t, IntraTransaction)]
            assert len(resolved_intra) >= 1, "Should have at least one IntraTransaction"

            # Verify the transaction has both crypto_sent and crypto_received
            tx = resolved_intra[0]
            assert tx.crypto_sent is not None and tx.crypto_sent != "Unknown", f"crypto_sent should be known: {tx.crypto_sent}"
            assert tx.crypto_received is not None and tx.crypto_received != "Unknown", f"crypto_received should be known: {tx.crypto_received}"
        finally:
            os.unlink(intra_csv_path)

    def test_two_way_transfer_resolution(self) -> None:
        """Test that two-way transfers (send + receive) resolve correctly."""
        # Create a temporary CSV with an InTransaction and OutTransaction with same unique_id
        # IN CSV: valid types are Buy, Income, Staking, Interest, Mining, Airdrop, Gift, Donation, Hardfork, Wages
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
transfer123,2022-01-15T10:00:00Z,BTC,Coinbase,User,Buy,40000,0.25,,,,,"""

        # OUT CSV: valid types are Sell, Fee, Lost, Donation, Gift
        out_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto Out No Fee,Crypto Fee,Crypto Out With Fee,USD Out No Fee,USD Fee,Notes
transfer123,2022-01-15T10:00:00Z,BTC,Binance,User,Sell,40000,0.25,0,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='_in.csv', delete=False) as f_in:
            f_in.write(in_csv_content)
            in_csv_path = f_in.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='_out.csv', delete=False) as f_out:
            f_out.write(out_csv_content)
            out_csv_path = f_out.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=in_csv_path, out_csv=out_csv_path)

            # The resolver should combine these into an IntraTransaction
            assert len(resolved) > 0, "Should have resolved transactions"

            # Should have at least one IntraTransaction (the resolved transfer)
            intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))
            assert intra_count >= 1, f"Expected at least 1 IntraTransaction from In+Out resolution, got {intra_count}"
        finally:
            os.unlink(in_csv_path)
            os.unlink(out_csv_path)


class TestPartialTransactions:
    """Tests for partial transaction handling."""

    def test_partial_transaction_sender_knows_less(self) -> None:
        """Test when sender knows less than receiver (e.g., network fees)."""
        # Sender knows they sent 0.5 BTC, but receiver got 0.499 BTC (fee taken)
        intra_csv_content = """Unique ID,Timestamp,Asset,From Exchange,From Holder,To Exchange,To Holder,Spot Price,Crypto Sent,Crypto Received,Notes
partial001,2022-01-20 12:00:00 +0000,BTC,SenderExchange,Sender,,,,0.5,,Sender sent 0.5 BTC,
partial001,2022-01-20 12:00:05 +0000,BTC,,,ReceiverExchange,Receiver,35000,,0.499,Receiver got 0.499 BTC (network fee deducted),"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(intra_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(intra_csv=csv_path)

            assert len(resolved) > 0, "Should have resolved transactions"

            # The resolver should merge these with resolved amounts
            intra_txs = [t for t in resolved if isinstance(t, IntraTransaction)]
            assert len(intra_txs) >= 1, "Should have at least one resolved IntraTransaction"
        finally:
            os.unlink(csv_path)

    def test_partial_transaction_receiver_knows_more(self) -> None:
        """Test when receiver knows more than sender (e.g., deposit confirmations)."""
        intra_csv_content = """Unique ID,Timestamp,Asset,From Exchange,From Holder,To Exchange,To Holder,Spot Price,Crypto Sent,Crypto Received,Notes
partial002,2022-01-21 14:00:00 +0000,ETH,SenderExchange,Sender,,,,2.0,,Sender sent 2 ETH,
partial002,2022-01-21 14:05:00 +0000,ETH,,,ReceiverExchange,Receiver,2000,,2.0,Receiver received 2 ETH,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(intra_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(intra_csv=csv_path)

            assert len(resolved) > 0, "Should have resolved transactions"

            # Check that ETH transactions exist
            eth_txs = [t for t in resolved if t.asset == "ETH"]
            assert len(eth_txs) >= 1, "Should have ETH transactions"
        finally:
            os.unlink(csv_path)

    def test_unmatched_partial_transaction(self) -> None:
        """Test unmatched partial transaction (no matching counterpart)."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
unmatched123,2022-01-22T15:00:00Z,BTC,Coinbase,User,Buy,45000,0.1,,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            # Should still have the transaction even without a match
            assert len(resolved) > 0, "Should have resolved transactions"
            assert any(t.unique_id == "unmatched123" for t in resolved), "Should have the unmatched transaction"
        finally:
            os.unlink(csv_path)


class TestMultipleAssets:
    """Tests for handling multiple assets across plugins."""

    def test_multiple_assets_btc_eth(self) -> None:
        """Test transactions with multiple assets (BTC and ETH)."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
btc001,2022-02-01T10:00:00Z,BTC,Coinbase,User,Buy,40000,0.5,,,,,Bought BTC
eth001,2022-02-01T11:00:00Z,ETH,Coinbase,User,Buy,2500,2.0,,,,,Bought ETH"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            # Verify transactions were loaded
            assert len(resolved) > 0, "Should have resolved transactions"

            # Extract unique assets
            assets = set(t.asset for t in resolved if t.asset)
            assert "BTC" in assets, f"BTC should be in output assets: {assets}"
            assert "ETH" in assets, f"ETH should be in output assets: {assets}"
        finally:
            os.unlink(csv_path)

    def test_cross_asset_transfer_independence(self) -> None:
        """Test that transfers of different assets are resolved independently."""
        # INTRA CSV: Move is valid only for IntraTransaction
        intra_csv_content = """Unique ID,Timestamp,Asset,From Exchange,From Holder,To Exchange,To Holder,Spot Price,Crypto Sent,Crypto Received,Notes
btc_transfer_001,2022-02-05T10:00:00Z,BTC,Binance,User1,,,40000,0.1,,BTC transfer,
btc_transfer_001,2022-02-05T10:00:05Z,BTC,,,Coinbase,User2,40000,,0.1,BTC received,
transfer_001,2022-02-05T11:00:00Z,ETH,Binance,User1,,,2500,1.0,,ETH transfer,
transfer_001,2022-02-05T11:00:05Z,ETH,,,Coinbase,User2,2500,,1.0,ETH received,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(intra_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(intra_csv=csv_path)

            assert len(resolved) > 0, "Should have resolved transactions"

            # Should have resolved both BTC and ETH transfers
            btc_txs = [t for t in resolved if t.asset == "BTC"]
            eth_txs = [t for t in resolved if t.asset == "ETH"]

            assert len(btc_txs) >= 1, "Should have BTC transactions"
            assert len(eth_txs) >= 1, "Should have ETH transactions"
        finally:
            os.unlink(csv_path)


class TestDifferentTransactionTypes:
    """Tests for handling different transaction types."""

    def test_buy_transaction(self) -> None:
        """Test Buy transaction type (InTransaction)."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
buy001,2022-03-01T10:00:00Z,BTC,Coinbase,User,Buy,45000,0.5,,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            # Find the Buy transaction
            buy_txs = [
                t for t in resolved
                if isinstance(t, InTransaction)
                and t.transaction_type
                and "buy" in t.transaction_type.lower()
            ]

            assert len(buy_txs) >= 1, f"Should have at least 1 Buy transaction, got {len(buy_txs)}"
        finally:
            os.unlink(csv_path)

    def test_sell_transaction(self) -> None:
        """Test Sell transaction type (OutTransaction)."""
        out_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto Out No Fee,Crypto Fee,Crypto Out With Fee,USD Out No Fee,USD Fee,Notes
sell001,2022-03-02T10:00:00Z,BTC,Coinbase,User,Sell,45000,0.5,0,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(out_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(out_csv=csv_path)

            # Find the Sell transaction
            sell_txs = [
                t for t in resolved
                if isinstance(t, OutTransaction)
                and t.transaction_type
                and "sell" in t.transaction_type.lower()
            ]

            assert len(sell_txs) >= 1, f"Should have at least 1 Sell transaction, got {len(sell_txs)}"
        finally:
            os.unlink(csv_path)

    def test_transfer_transaction(self) -> None:
        """Test Transfer/Move transaction type (IntraTransaction)."""
        # Move is valid only for IntraTransaction - two matching transactions get resolved
        intra_csv_content = """Unique ID,Timestamp,Asset,From Exchange,From Holder,To Exchange,To Holder,Spot Price,Crypto Sent,Crypto Received,Notes
transfer001,2022-03-03T10:00:00Z,BTC,Coinbase,User1,,,40000,0.5,,Transfer out,
transfer001,2022-03-03T10:00:05Z,BTC,,,Binance,User2,40000,,0.5,Transfer in,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(intra_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(intra_csv=csv_path)

            # Find resolved IntraTransactions (from matching two-way transfer)
            move_txs = [t for t in resolved if isinstance(t, IntraTransaction)]

            assert len(move_txs) >= 1, f"Should have at least 1 resolved IntraTransaction"

            # Verify the resolved transaction has proper from/to exchanges
            tx = move_txs[0]
            assert tx.from_exchange == "Coinbase" or tx.to_exchange == "Binance", "Should have proper exchange info"
        finally:
            os.unlink(csv_path)

    def test_income_transaction(self) -> None:
        """Test Income transaction type (InTransaction)."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
income001,2022-03-04T10:00:00Z,ADA,Coinbase,User,Income,0.35,100.0,,,,,Staking reward"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            # Find Income transactions
            income_txs = [
                t for t in resolved
                if isinstance(t, InTransaction)
                and t.transaction_type
                and "income" in t.transaction_type.lower()
            ]

            assert len(income_txs) >= 1, f"Should have at least 1 Income transaction"
        finally:
            os.unlink(csv_path)

    def test_fee_transaction(self) -> None:
        """Test Fee transaction type (OutTransaction)."""
        out_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto Out No Fee,Crypto Fee,Crypto Out With Fee,USD Out No Fee,USD Fee,Notes
expense001,2022-03-05T10:00:00Z,BTC,Coinbase,User,Fee,40000,0.01,0,,,,,Network fee"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(out_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(out_csv=csv_path)

            # Find Fee transactions
            fee_txs = [
                t for t in resolved
                if isinstance(t, OutTransaction)
                and t.transaction_type
                and t.transaction_type.lower() == "fee"
            ]

            assert len(fee_txs) >= 1, f"Should have at least 1 Fee transaction"
        finally:
            os.unlink(csv_path)

    def test_staking_transaction(self) -> None:
        """Test Staking transaction type (InTransaction)."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
staking001,2022-03-06T10:00:00Z,ADA,Coinbase,User,Staking,0.35,50.0,,,,,Staking reward"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            # Find Staking transactions
            staking_txs = [
                t for t in resolved
                if isinstance(t, InTransaction)
                and t.transaction_type
                and "staking" in t.transaction_type.lower()
            ]

            assert len(staking_txs) >= 1, f"Should have at least 1 Staking transaction"
        finally:
            os.unlink(csv_path)

    def test_mixed_transaction_types_in_single_run(self) -> None:
        """Test all transaction types in a single pipeline run."""
        # IN CSV: Buy, Income, Staking are valid
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
buy001,2022-03-10T10:00:00Z,BTC,Coinbase,User,Buy,45000,0.5,,,,,
income001,2022-03-10T11:00:00Z,ETH,Coinbase,User,Income,2000,1.0,,,,,Staking
staking001,2022-03-10T12:00:00Z,ADA,Coinbase,User,Staking,0.35,50.0,,,,,"""

        # OUT CSV: Sell, Fee are valid
        out_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto Out No Fee,Crypto Fee,Crypto Out With Fee,USD Out No Fee,USD Fee,Notes
sell001,2022-03-10T13:00:00Z,BTC,Coinbase,User,Sell,45000,0.2,0,,,,,
fee001,2022-03-10T14:00:00Z,BTC,Coinbase,User,Fee,45000,0.01,0,,,,,Fee"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='_in.csv', delete=False) as f_in:
            f_in.write(in_csv_content)
            in_csv_path = f_in.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='_out.csv', delete=False) as f_out:
            f_out.write(out_csv_content)
            out_csv_path = f_out.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=in_csv_path, out_csv=out_csv_path)

            # Verify all transaction types are present
            in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
            out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))

            assert in_count >= 3, f"Expected at least 3 InTransactions, got {in_count}"
            assert out_count >= 2, f"Expected at least 2 OutTransactions, got {out_count}"

            # Check for specific transaction types
            transaction_types = set(
                t.transaction_type for t in resolved
                if t.transaction_type and t.transaction_type != "Unknown"
            )

            assert "Buy" in transaction_types, f"Should have Buy type: {transaction_types}"
            assert "Sell" in transaction_types, f"Should have Sell type: {transaction_types}"
            assert "Income" in transaction_types, f"Should have Income type: {transaction_types}"
            assert "Fee" in transaction_types, f"Should have Fee type: {transaction_types}"
            assert "Staking" in transaction_types, f"Should have Staking type: {transaction_types}"
        finally:
            os.unlink(in_csv_path)
            os.unlink(out_csv_path)


class TestMultiPluginIntegration:
    """Tests for multi-plugin integration scenarios."""

    @pytest.fixture
    def manual_in_csv_path(self) -> str:
        return "input/test_manual_in.csv"

    @pytest.fixture
    def manual_out_csv_path(self) -> str:
        return "input/test_manual_out.csv"

    @pytest.fixture
    def manual_intra_csv_path(self) -> str:
        return "input/test_manual_intra.csv"

    def test_manual_plugin_comprehensive(self, manual_in_csv_path: str, manual_out_csv_path: str, manual_intra_csv_path: str) -> None:
        """Test manual plugin with all transaction types."""
        resolved = _run_manual_full_pipeline(
            in_csv=manual_in_csv_path,
            out_csv=manual_out_csv_path,
            intra_csv=manual_intra_csv_path,
        )

        assert len(resolved) > 0, "Should have resolved transactions"

        # Verify all transaction types
        in_count = sum(1 for t in resolved if isinstance(t, InTransaction))
        out_count = sum(1 for t in resolved if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in resolved if isinstance(t, IntraTransaction))

        assert in_count >= 2, f"Expected at least 2 InTransactions, got {in_count}"
        assert out_count >= 1, f"Expected at least 1 OutTransaction, got {out_count}"
        assert intra_count >= 1, f"Expected at least 1 IntraTransaction, got {intra_count}"

    def test_binance_plugin_comprehensive(self) -> None:
        """Test Binance plugin with various transaction types."""
        binance_autoinvest = "input/test_binance_autoinvest.csv"
        binance_betheth = "input/test_binance_betheth.csv"

        resolved = _run_binance_full_pipeline(
            autoinvest_csv=binance_autoinvest,
            betheth_csv=binance_betheth,
        )

        assert len(resolved) > 0, "Should have resolved transactions"

        # Binance should have multiple assets
        assets = set(t.asset for t in resolved if t.asset)
        assert len(assets) >= 2, f"Should have multiple assets: {assets}"

    def test_pionex_plugin_comprehensive(self) -> None:
        """Test Pionex plugin with trades and transfers."""
        pionex_trades = "input/test_pionex_trades.csv"
        pionex_transfers = "input/test_pionex_transfers.csv"

        resolved = _run_pionex_full_pipeline(
            trades_csv=pionex_trades,
            transfers_csv=pionex_transfers,
        )

        # Pionex may have both InTransaction and OutTransaction (trades)
        assert len(resolved) > 0, "Should have resolved transactions"


class TestODSGeneration:
    """Tests for ODS output generation from multi-plugin scenarios."""

    def test_ods_output_multi_transaction_types(self) -> None:
        """Test ODS generation with multiple transaction types."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
buy001,2022-04-01T10:00:00Z,BTC,Coinbase,User,Buy,45000,0.5,,,,,
buy002,2022-04-02T10:00:00Z,ETH,Coinbase,User,Buy,2500,1.0,,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            with tempfile.TemporaryDirectory() as tmpdir:
                dali_configuration: Dict[str, Any] = {
                    Keyword.NATIVE_FIAT.value: "USD",
                }

                generate_input_file(
                    output_dir_path=tmpdir,
                    output_file_prefix="test_multi_",
                    output_file_name="crypto_data.ods",
                    transactions=resolved,
                    global_configuration=dali_configuration,
                )

                ods_path = os.path.join(tmpdir, "test_multi_crypto_data.ods")
                assert os.path.exists(ods_path), f"ODS file should exist at {ods_path}"
                assert os.path.getsize(ods_path) > 0, "ODS file should not be empty"
        finally:
            os.unlink(csv_path)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_unique_id_transactions(self) -> None:
        """Test handling of transactions with empty unique IDs."""
        # Manual plugin can have empty unique IDs - they become "__unknown"
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
,2022-05-01T10:00:00Z,BTC,Coinbase,User,Buy,45000,0.1,,,,,No unique ID
,2022-05-02T10:00:00Z,BTC,Coinbase,User,Buy,45000,0.2,,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            # Should handle empty unique IDs gracefully
            assert len(resolved) > 0, "Should have resolved transactions"
        finally:
            os.unlink(csv_path)

    def test_same_timestamp_different_assets(self) -> None:
        """Test transactions with same timestamp but different assets."""
        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
btc_001,2022-05-10T10:00:00Z,BTC,Coinbase,User,Buy,45000,0.1,,,,,
eth_001,2022-05-10T10:00:00Z,ETH,Coinbase,User,Buy,2500,1.0,,,,,
ada_001,2022-05-10T10:00:00Z,ADA,Coinbase,User,Buy,0.35,100.0,,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(in_csv=csv_path)

            assert len(resolved) >= 3, "Should have all three asset transactions"

            # Verify all three assets are present
            assets = set(t.asset for t in resolved if t.asset)
            assert "BTC" in assets, "Should have BTC"
            assert "ETH" in assets, "Should have ETH"
            assert "ADA" in assets, "Should have ADA"
        finally:
            os.unlink(csv_path)


class TestMockPairConverter:
    """Tests for the MockPairConverter used in E2E tests."""

    def test_mock_converter_returns_prices(self) -> None:
        """Test that mock converter returns expected prices."""
        mock = MockPairConverter(btc_price="50000", eth_price="3000")

        from typing import Any
        result = mock.get_conversion_rate(
            "2022-01-01", "BTC", "USD", "test_exchange"
        )

        assert result == RP2Decimal("50000")

        result = mock.get_conversion_rate(
            "2022-01-01", "ETH", "USD", "test_exchange"
        )

        assert result == RP2Decimal("3000")

    def test_mock_converter_unknown_pair(self) -> None:
        """Test that mock converter returns None for unknown pairs."""
        mock = MockPairConverter()

        result = mock.get_conversion_rate(
            "2022-01-01", "UNKNOWN", "USD", "test_exchange"
        )

        assert result is None

    def test_explicit_mock_converter_in_pipeline(self) -> None:
        """Test explicit mock converter in full pipeline."""
        mock_converter = MagicMock()
        mock_converter.name.return_value = "TestMockConverter"
        mock_converter.cache_key.return_value = "test_mock"
        mock_converter.get_historic_bar_from_native_source.return_value = None

        def mock_get_conversion_rate(timestamp: Any, from_asset: str, to_asset: str, exchange: str) -> Optional[RP2Decimal]:
            if from_asset == "BTC" and to_asset == "USD":
                return RP2Decimal("50000")
            return None

        mock_converter.get_conversion_rate = mock_get_conversion_rate
        mock_converter.optimize.return_value = None
        mock_converter.save_historical_price_cache.return_value = None

        in_csv_content = """Unique ID,Timestamp,Asset,Exchange,Holder,Transaction Type,Spot Price,Crypto In,Crypto Fee,USD In No Fee,USD In With Fee,USD Fee,Notes
test001,2022-06-01T10:00:00Z,BTC,Coinbase,User,Buy,50000,0.1,,,,,"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(in_csv_content)
            csv_path = f.name

        try:
            resolved = _run_manual_full_pipeline(
                in_csv=csv_path,
                mock_converter=mock_converter,
            )

            assert len(resolved) > 0
        finally:
            os.unlink(csv_path)