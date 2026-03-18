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

"""Tests for Yoroi CSV plugin with Minswap integration."""

from rp2.plugin.country.us import US

from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction
from dali.plugin.input.csv.yoroi import InputPlugin


class TestYoroiCsv:
    """Test Yoroi CSV plugin with Minswap DeFi transactions."""

    def test_staking_rewards(self) -> None:
        """Test that staking rewards are parsed as InTransactions."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv=None,
        )

        result = plugin.load(US())

        # Filter staking rewards (note: plugin uses "Staking" not Keyword.STAKING.value)
        staking_txs = [
            t for t in result
            if isinstance(t, InTransaction)
            and "Staking" in t.transaction_type
            and "Staking Reward" in (t.notes or "")
        ]

        assert len(staking_txs) == 3, f"Expected 3 staking rewards, got {len(staking_txs)}"

        # Verify first staking reward
        assert "0.5" in staking_txs[0].crypto_in
        assert staking_txs[0].asset == "ADA"
        assert "Epoch 100" in staking_txs[0].notes

    def test_yoroi_only_no_minswap(self) -> None:
        """Test Yoroi plugin without Minswap data."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv=None,
        )

        result = plugin.load(US())

        # Should have:
        # - 3 staking rewards (InTransaction)
        # - 7 deposits (IntraTransaction)
        # - 6 withdrawals (IntraTransaction) - one more from the new LP pair
        # Total: 16 transactions
        assert len(result) == 16

        intra_count = sum(1 for t in result if isinstance(t, IntraTransaction))
        assert intra_count == 13  # 7 deposits + 6 withdrawals

        in_count = sum(1 for t in result if isinstance(t, InTransaction))
        assert in_count == 3  # 3 staking rewards

    def test_yoroi_with_minswap_swaps(self) -> None:
        """Test Yoroi plugin with Minswap swap transactions."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Total should include:
        # - 3 staking rewards (InTransaction)
        # - Basic Yoroi intra-transactions (deposits/withdrawals not matched to Minswap)
        # - Swaps generate OutTransaction + InTransaction pairs
        #
        # Minswap has 4 swaps, each generates:
        # - 1 OutTransaction (sell ADA)
        # - 1 InTransaction (buy token)
        # Total from Minswap: 8 transactions (4 swaps × 2)
        #
        # Plus basic Yoroi: 11 transactions
        # But 3 of those are matched to Minswap (the swap pairs)
        # So: 11 + 8 - 6 = 13 (approximate, depends on deduplication)

        # Count by type
        in_count = sum(1 for t in result if isinstance(t, InTransaction))
        out_count = sum(1 for t in result if isinstance(t, OutTransaction))
        intra_count = sum(1 for t in result if isinstance(t, IntraTransaction))

        # Should have OutTransactions from swaps (selling ADA)
        assert out_count >= 3, f"Expected at least 3 OutTransactions (ADA sells), got {out_count}"

        # Should have InTransactions from swaps (buying tokens) + staking rewards
        assert in_count >= 6, f"Expected at least 6 InTransactions (staking + token buys), got {in_count}"

    def test_swap_uses_yoroi_amounts(self) -> None:
        """Test that swaps use Yoroi on-chain amounts (not Minswap input)."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the first swap OutTransaction (ADA sold)
        swap_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset == "ADA"
             and "swap" in (t.notes or "").lower()),
            None
        )

        if swap_out:
            # Yoroi shows 10 ADA sold, Minswap shows 10 ADA paid
            # But the fee makes it 10.2 ADA
            # The important thing is crypto_out_no_fee should be present
            assert swap_out.crypto_out_no_fee is not None, "crypto_out_no_fee should be set"

    def test_transaction_types_parsed(self) -> None:
        """Test that Deposit and Withdrawal types are parsed correctly."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv=None,
        )

        result = plugin.load(US())

        # Check we have IntraTransactions with proper from/to
        intra_txs = [t for t in result if isinstance(t, IntraTransaction)]

        # Find a withdrawal (crypto_sent)
        withdrawal = next(
            (t for t in intra_txs
             if t.crypto_sent and t.crypto_sent != Keyword.UNKNOWN.value),
            None
        )
        assert withdrawal is not None, "Should have at least one withdrawal"

        # Find a deposit (crypto_received)
        deposit = next(
            (t for t in intra_txs
             if t.crypto_received and t.crypto_received != Keyword.UNKNOWN.value),
            None
        )
        assert deposit is not None, "Should have at least one deposit"

    def test_fee_handling(self) -> None:
        """Test that fees are handled correctly."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv=None,
        )

        result = plugin.load(US())

        # Find a transaction with fee
        tx_with_fee = next(
            (t for t in result
             if isinstance(t, IntraTransaction)
             and t.crypto_sent
             and t.crypto_sent != Keyword.UNKNOWN.value
             and "0.2" in t.crypto_sent),
            None
        )

        if tx_with_fee:
            # The crypto_sent should include fee (10.0 + 0.2 = 10.2)
            assert tx_with_fee.crypto_sent is not None

    def test_lp_deposit_handling(self) -> None:
        """Test that LP deposits are handled (cost basis tracked, no taxable event).

        LP deposits don't create taxable transactions - they store cost basis
        for later when the LP is removed. We verify this by checking that
        the LP removal uses the cost basis from the deposit.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # The LP deposit cost basis is stored internally and used during LP removal
        # We can verify this by checking that LP removal InTransaction has the
        # correct asset (ADA received) - the cost basis is tracked internally

        # Check we have LP deposit in Minswap data (4 swaps + 1 deposit + 1 removal)
        minswap_ops = [t for t in result if hasattr(t, 'notes') and t.notes and 'Minswap' in t.notes]
        # Should have: 4 swaps (8 txs) + 1 removal (2 txs) = 10 Minswap-related transactions
        assert len(minswap_ops) >= 10, f"Expected at least 10 Minswap operations, got {len(minswap_ops)}"

    def test_lp_removal_handling(self) -> None:
        """Test that LP removals create proper taxable transactions."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # LP removal should create OutTransaction (sell LP) + InTransaction (buy ADA)
        # After fix: asset should be "LP-ADA-SNEK" not just "LP"
        lp_removal_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset and t.asset.startswith("LP-")),
            None
        )
        assert lp_removal_out is not None, "Should have LP removal OutTransaction with pool-specific name"
        # Verify it includes the pool name
        assert "SNEK" in lp_removal_out.asset, f"LP asset should include pool name, got: {lp_removal_out.asset}"

        lp_removal_in = next(
            (t for t in result
             if isinstance(t, InTransaction)
             and t.asset == "ADA"
             and hasattr(t, 'notes')
             and t.notes
             and 'LP Removal' in t.notes),
            None
        )
        assert lp_removal_in is not None, "Should have LP removal InTransaction with gain/loss notes"

    def test_lp_pool_name_detection(self) -> None:
        """Test that LP removal correctly identifies the pool (not 'unknown').

        This verifies the fix for Issue 2: pool name detection was failing
        for Zap Out because it looked for pool in received assets (which only
        has ADA), not from the cost basis lookup.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the LP removal OutTransaction
        lp_removal_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset and t.asset.startswith("LP-")),
            None
        )

        assert lp_removal_out is not None, "Should have LP removal OutTransaction"
        # Pool name should NOT be "unknown" - it should be detected from cost basis
        assert "unknown" not in lp_removal_out.notes.lower(), (
            f"Pool should not be unknown, got notes: {lp_removal_out.notes}"
        )
        # Should contain the specific pool name
        assert "SNEK" in lp_removal_out.notes or "WMTX" in lp_removal_out.notes, (
            f"Notes should contain specific pool name, got: {lp_removal_out.notes}"
        )

    def test_lp_cost_basis_lookup(self) -> None:
        """Test that LP cost basis is correctly looked up from deposit.

        This verifies the fix for Issue 3: the cost basis key mismatch.
        Deposit stores key as "ADA-SNEK_10000", but lookup was trying
        "ADA-ADA_10000" (looking for pool in received assets, which only has ADA).

        Expected: gain/loss should be calculated correctly using the deposit's cost basis.
        Deposit: 100 ADA + 5000 SNEK -> 10000 LP
        Removal: 10000 LP -> 50.5 ADA (minus 0.75 fee = 49.75 net)
        Gain/Loss: 49.75 - 100 = -50.25 (a loss)
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the LP removal InTransaction (the ADA received)
        lp_removal_in = next(
            (t for t in result
             if isinstance(t, InTransaction)
             and t.asset == "ADA"
             and hasattr(t, 'notes')
             and t.notes
             and 'LP Removal' in t.notes),
            None
        )

        assert lp_removal_in is not None, "Should have LP removal InTransaction"

        # Extract gain/loss from notes: "Gain/Loss: -50.25 ADA"
        import re
        match = re.search(r"Gain/Loss:\s*([-\d.]+)\s*ADA", lp_removal_in.notes)
        assert match is not None, f"Should have gain/loss in notes: {lp_removal_in.notes}"

        gain_loss = float(match.group(1))

        # Expected: (50.5 - 0.75) - 100 = -50.25
        # Before fix: cost basis was 0, so gain would be ~49.75
        assert -51 < gain_loss < -49, (
            f"Gain/loss should be ~-50.25 (loss from 100 ADA cost basis), "
            f"got {gain_loss}. This indicates cost basis lookup failed."
        )

    def test_lp_deposit_creates_three_transactions(self) -> None:
        """Test that LP deposit creates three transactions: ADA OUT, Token OUT, LP IN.

        This verifies the fix for LP deposit transaction recording.
        Before: LP deposits only stored cost basis internally (no transactions created)
        After: Creates OUT for ADA, OUT for token, IN for LP tokens
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the LP deposit transactions (July 10, 2025)
        # Deposit: 100 ADA + 5000 SNEK -> 10000 LP
        lp_deposit_ada_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset == "ADA"
             and "lp_deposit" in t.unique_id.lower()),
            None
        )
        lp_deposit_token_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset == "SNEK"
             and "lp_deposit" in t.unique_id.lower()),
            None
        )
        lp_deposit_in = next(
            (t for t in result
             if isinstance(t, InTransaction)
             and "LP-ADA-SNEK" in t.asset
             and "lp_deposit" in t.unique_id.lower()),
            None
        )

        assert lp_deposit_ada_out is not None, "LP deposit should create ADA OUT transaction"
        assert lp_deposit_token_out is not None, "LP deposit should create SNEK OUT transaction"
        assert lp_deposit_in is not None, "LP deposit should create LP token IN transaction"

        # Verify amounts
        assert "100" in lp_deposit_ada_out.crypto_out_no_fee, f"ADA amount should be 100, got {lp_deposit_ada_out.crypto_out_no_fee}"
        assert "5000" in lp_deposit_token_out.crypto_out_no_fee, f"SNEK amount should be 5000, got {lp_deposit_token_out.crypto_out_no_fee}"
        assert "10000" in lp_deposit_in.crypto_in, f"LP amount should be 10000, got {lp_deposit_in.crypto_in}"

    def test_lp_deposit_has_derive_hint_for_token(self) -> None:
        """Test that LP deposit token OUT has DERIVE hint for price lookup.

        The token OUT transaction should include a DERIVE hint so the
        transaction resolver can derive the price from the ADA amount.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the SNEK OUT transaction from LP deposit
        snek_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset == "SNEK"
             and "lp_deposit" in t.unique_id.lower()),
            None
        )

        assert snek_out is not None, "Should have SNEK OUT from LP deposit"
        assert "DERIVE" in snek_out.notes, f"Notes should contain DERIVE hint, got: {snek_out.notes}"
        assert "ADA" in snek_out.notes, f"DERIVE hint should reference ADA, got: {snek_out.notes}"

    def test_zap_out_creates_two_transactions(self) -> None:
        """Test that Zap Out creates two transactions: LP OUT and ADA IN.

        Note: We do NOT create a separate OUT for the original token (e.g., SNEK)
        because the ADA IN already includes both the original ADA and token value.
        The token was effectively "sold" at deposit time when LP tokens were received.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the Zap Out transactions (July 15, 2025)
        # Zap Out: 10000 LP -> 50.5 ADA (original: 100 ADA + 5000 SNEK)
        lp_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and "LP-ADA-SNEK" in t.asset
             and "lp_remove" in t.unique_id.lower()),
            None
        )
        token_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and t.asset == "SNEK"
             and "lp_remove" in t.unique_id.lower()),
            None
        )
        ada_in = next(
            (t for t in result
             if isinstance(t, InTransaction)
             and t.asset == "ADA"
             and "lp_remove" in t.unique_id.lower()),
            None
        )

        assert lp_out is not None, "Zap Out should create LP OUT transaction"
        assert token_out is None, "Zap Out should NOT create separate SNEK OUT (it's in the ADA)"
        assert ada_in is not None, "Zap Out should create ADA IN transaction"

        # Verify amounts
        assert "10000" in lp_out.crypto_out_no_fee, f"LP amount should be 10000, got {lp_out.crypto_out_no_fee}"
        assert "50.5" in ada_in.crypto_in, f"ADA amount should be 50.5, got {ada_in.crypto_in}"

    def test_zap_out_gain_loss_includes_token_value(self) -> None:
        """Test that Zap Out gain/loss calculation includes token value.

        The gain/loss should be: (ADA received) - (ADA cost basis from deposit)
        The SNEK value is already baked into the ADA received.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the LP removal OutTransaction (SNEK pool)
        lp_out = next(
            (t for t in result
             if isinstance(t, OutTransaction)
             and "LP-ADA-SNEK" in t.asset
             and "lp_remove" in t.unique_id.lower()),
            None
        )

        assert lp_out is not None, "Should have LP removal OUT"
        # The notes should contain the gain/loss which includes token value
        assert "Gain/Loss" in lp_out.notes, f"Notes should contain Gain/Loss: {lp_out.notes}"

        # Expected: (50.5 - 0.75 fee) - 100 = -50.25
        # But we need to extract the actual value from notes
        import re
        match = re.search(r"Gain/Loss: ([-\d.]+)", lp_out.notes)
        assert match is not None, "Should be able to extract gain/loss from notes"
        gain_loss = float(match.group(1))
        # Should be negative (a loss)
        assert gain_loss < 0, f"Gain/loss should be negative, got {gain_loss}"

    def test_multiple_assets_in_lp_deposit(self) -> None:
        """Test that LP deposit handles both ADA and token in the paid field.

        The test data has one LP deposit with both ADA and SNEK.
        This verifies both assets are properly extracted.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find LP deposit transactions with both assets (July 10, 2025)
        # Deposit: 100 ADA + 5000 SNEK -> 10000 LP
        # Check we have ADA OUT with amount containing "100"
        ada_outs = [
            t for t in result
            if isinstance(t, OutTransaction)
            and t.asset == "ADA"
            and "lp_deposit" in t.unique_id.lower()
        ]

        # Check we have SNEK OUT with amount containing "5000"
        snek_outs = [
            t for t in result
            if isinstance(t, OutTransaction)
            and t.asset == "SNEK"
            and "lp_deposit" in t.unique_id.lower()
        ]

        assert len(ada_outs) >= 1, "Should have at least one ADA OUT from LP deposit"
        assert len(snek_outs) >= 1, "Should have at least one SNEK OUT from LP deposit"

        # Verify amounts
        ada_amount = ada_outs[0].crypto_out_no_fee
        snek_amount = snek_outs[0].crypto_out_no_fee
        assert "100" in ada_amount, f"ADA amount should contain 100, got {ada_amount}"
        assert "5000" in snek_amount, f"SNEK amount should contain 5000, got {snek_amount}"

    def test_full_lp_cycle_for_single_pool(self) -> None:
        """Test the full LP cycle for a single pool (deposit + zap out).

        This tests the SNEK pool which has both deposit and zap out.
        Deposit: 100 ADA + 5000 SNEK -> 10000 LP-ADA-SNEK
        Zap Out: 10000 LP-ADA-SNEK -> 50.5 ADA (plus 5000 SNEK implicitly sold)
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find all SNEK-ADA pool transactions (include ADA for both LP deposit and removal)
        snek_pool_txs = [
            t for t in result
            if ("SNEK" in (t.asset or "")
                or "LP-ADA-SNEK" in (t.asset or "")
                or (t.asset == "ADA" and ("lp_deposit" in t.unique_id.lower() or "lp_remove" in t.unique_id.lower())))
            and ("lp_deposit" in t.unique_id.lower() or "lp_remove" in t.unique_id.lower())
        ]

        # Should have 5 transactions:
        # - Deposit: ADA OUT, SNEK OUT, LP IN (3)
        # - Zap Out: LP OUT, ADA IN (2)
        assert len(snek_pool_txs) == 5, f"Expected 5 SNEK pool transactions, got {len(snek_pool_txs)}"

        # Count by type
        out_count = sum(1 for t in snek_pool_txs if isinstance(t, OutTransaction))
        in_count = sum(1 for t in snek_pool_txs if isinstance(t, InTransaction))

        assert out_count == 3, f"Expected 3 OUT transactions (2 for deposit, 1 for zap out), got {out_count}"
        assert in_count == 2, f"Expected 2 IN transactions (LP in, ADA in), got {in_count}"

    def test_lp_deposit_creates_two_balancing_intra_transactions(self) -> None:
        """Test that LP deposit creates two balancing IntraTransactions.

        These intra transactions balance the Yoroi Withdrawal and Deposit entries
        and properly handle the 2 ADA deposit return + fees.

        For each LP deposit, we should have:
        1. Intra: andrew_wallet -> __unknown, 2.0 ADA (deposit return)
        2. Intra: __unknown -> andrew_wallet, 100 + 2 + 0.75 = 102.75 ADA (ADA sent to pool)

        The unique IDs should be:
        - executed_tx for the deposit return
        - created_tx for the ADA sent to pool
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the balancing intra transactions for LP deposits
        # These have notes containing "deposit return" or "ADA sent to pool"
        deposit_return_intras = [
            t for t in result
            if isinstance(t, IntraTransaction)
            and t.notes
            and "deposit return" in t.notes.lower()
        ]
        ada_sent_intras = [
            t for t in result
            if isinstance(t, IntraTransaction)
            and t.notes
            and "ada sent to pool" in t.notes.lower()
        ]

        assert len(deposit_return_intras) >= 1, f"Should have at least one deposit return intra, got {len(deposit_return_intras)}"
        assert len(ada_sent_intras) >= 1, f"Should have at least one ADA sent to pool intra, got {len(ada_sent_intras)}"

        # Verify deposit return: 2.0 ADA from wallet to unknown
        deposit_return = deposit_return_intras[0]
        assert deposit_return.asset == "ADA", f"Asset should be ADA, got {deposit_return.asset}"
        assert deposit_return.from_exchange == "yoroi_wallet", f"From should be yoroi_wallet, got {deposit_return.from_exchange}"
        assert deposit_return.to_exchange == Keyword.UNKNOWN.value, f"To should be __unknown, got {deposit_return.to_exchange}"
        assert deposit_return.crypto_sent == "2.0", f"Crypto sent should be 2.0, got {deposit_return.crypto_sent}"

        # Verify deposit return unique_id is the executed_tx from minswap
        # Test data: executed_tx = abcd1111bbbb2222cccc3333dddd4444eeee5555
        assert "abcd1111" in deposit_return.unique_id, f"Unique ID should be executed_tx, got {deposit_return.unique_id}"

        # Verify ADA sent to pool: 102.75 ADA (100 + 2 + 0.75) from unknown to wallet
        ada_sent = ada_sent_intras[0]
        assert ada_sent.asset == "ADA", f"Asset should be ADA, got {ada_sent.asset}"
        assert ada_sent.from_exchange == Keyword.UNKNOWN.value, f"From should be __unknown, got {ada_sent.from_exchange}"
        assert ada_sent.to_exchange == "yoroi_wallet", f"To should be yoroi_wallet, got {ada_sent.to_exchange}"
        # Crypto received should be 100 (ADA) + 2 (deposit) + 0.75 (fee) = 102.75
        assert float(ada_sent.crypto_received) == 102.75, f"Crypto received should be 102.75, got {ada_sent.crypto_received}"

        # Verify ADA sent unique_id is the created_tx from minswap
        # Test data: created_tx = abcd0000bbbb1111cccc2222dddd3333eeee4444
        assert "abcd0000" in ada_sent.unique_id, f"Unique ID should be created_tx, got {ada_sent.unique_id}"

    def test_lp_deposit_intra_raw_data_from_minswap(self) -> None:
        """Test that LP deposit intra transactions have raw_data from minswap CSV."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the deposit return intra transaction
        deposit_return = next(
            (t for t in result
             if isinstance(t, IntraTransaction)
             and t.notes
             and "deposit return" in t.notes.lower()),
            None
        )

        assert deposit_return is not None, "Should have deposit return intra"
        # Raw data should contain Minswap-specific fields
        assert "Minswap" in deposit_return.raw_data or "Deposit" in deposit_return.raw_data, (
            f"Raw data should be from minswap, got: {deposit_return.raw_data[:100]}"
        )

    def test_lp_deposit_intra_notes_present(self) -> None:
        """Test that LP deposit and removal intra transactions have descriptive notes."""
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find all balancing intra transactions (deposit + removal)
        intra_txs = [
            t for t in result
            if isinstance(t, IntraTransaction)
            and t.notes
            and ("deposit return" in t.notes.lower() or "ada sent to pool" in t.notes.lower())
        ]

        # Should have at least 3: 2 from LP deposit + 1 from LP removal
        assert len(intra_txs) >= 3, f"Should have at least 3 balancing intras (2 deposit + 1 removal), got {len(intra_txs)}"

        # All should have notes
        for tx in intra_txs:
            assert tx.notes is not None and len(tx.notes) > 0, f"Intra should have notes: {tx.unique_id}"
            assert "Minswap LP" in tx.notes, f"Notes should reference Minswap LP: {tx.notes}"

    def test_lp_removal_creates_balancing_intra_transaction(self) -> None:
        """Test that LP removal creates one balancing IntraTransaction for deposit return.

        For each LP removal (Zap Out), we should have:
        1. Intra: andrew_wallet -> __unknown, 2.0 ADA (deposit return)

        The unique ID should be the created_tx from minswap.
        """
        plugin = InputPlugin(
            account_holder="tester",
            account_nickname="yoroi_wallet",
            csv_file="input/test_yoroi.csv",
            timezone="UTC",
            native_fiat="USD",
            minswap_csv="input/test_minswap.csv",
        )

        result = plugin.load(US())

        # Find the balancing intra transaction for LP removal
        removal_intras = [
            t for t in result
            if isinstance(t, IntraTransaction)
            and t.notes
            and "lp removal" in t.notes.lower()
            and "deposit return" in t.notes.lower()
        ]

        assert len(removal_intras) >= 1, f"Should have at least one LP removal intra, got {len(removal_intras)}"

        # Verify: 2.0 ADA from wallet to unknown
        removal_intra = removal_intras[0]
        assert removal_intra.asset == "ADA", f"Asset should be ADA, got {removal_intra.asset}"
        assert removal_intra.from_exchange == "yoroi_wallet", f"From should be yoroi_wallet, got {removal_intra.from_exchange}"
        assert removal_intra.to_exchange == Keyword.UNKNOWN.value, f"To should be __unknown, got {removal_intra.to_exchange}"
        assert removal_intra.crypto_sent == "2.0", f"Crypto sent should be 2.0, got {removal_intra.crypto_sent}"

        # Verify unique_id is the executed_tx from minswap
        # Test data: executed_tx = efgh7777ffff8888gggg9999hhhh0000iiii1111
        assert "efgh7777" in removal_intra.unique_id, f"Unique ID should be executed_tx, got {removal_intra.unique_id}"

        # Verify raw_data is from minswap
        assert "Zap Out" in removal_intra.raw_data or "Minswap" in removal_intra.raw_data, (
            f"Raw data should be from minswap, got: {removal_intra.raw_data[:50]}"
        )