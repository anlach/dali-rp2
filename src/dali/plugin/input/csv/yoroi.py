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

# This plugin parses the export from Yoroi wallet AND Minswap DeFi transactions.
# CSV Format (Yoroi):
# 0: "Type (Trade, IN or OUT)",
# 1: "Buy Amount",
# 2: "Buy Cur.",
# 3: "Sell Amount",
# 4: "Sell Cur.",
# 5: "Fee Amount (optional)",
# 6: "Fee Cur. (optional)",
# 7: "Exchange (optional)",
# 8: "Trade Group (optional)",
# 9: "Comment (optional)",
# 10: "Date",
# 11: "ID"
#
# CSV Format (Minswap):
# - Created At, Created Tx, Protocol, Order Type, Status, Paid, Receive, Change Amount, Execution Fees, Executed Tx, Executed At

import logging
import re
from csv import reader
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pytz
from dateutil.parser import parse
from rp2.abstract_country import AbstractCountry
from rp2.logger import create_logger
from rp2.rp2_decimal import ZERO, RP2Decimal

from dali.abstract_input_plugin import AbstractInputPlugin
from dali.abstract_transaction import AbstractTransaction
from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction

_SENT: str = "Withdrawal"
_RECV: str = "Deposit"

# Cardano smart contract deposit return (always 2 ADA)
_CARDANO_DEPOSIT_RETURN: float = 2.0

# Minswap order types
_ORDER_TYPE_MARKET: str = "Market"
_ORDER_TYPE_LIMIT: str = "Limit"
_ORDER_TYPE_ZAP_OUT: str = "Zap Out"
_ORDER_TYPE_DEPOSIT: str = "Deposit"

# LP cost basis storage (for calculating gains on removal)
_LP_COST_BASES: Dict[str, Dict] = {}  # lp_token_amount -> {ada_cost, token_cost, token_currency, timestamp, pool, deposit_tx}


@dataclass
class Asset:
    """Represents a single asset with amount and currency."""

    amount: float
    currency: str
    raw: str  # Original string (may be in Lovelace for ADA)

    def is_lp_token(self) -> bool:
        """Check if this is an LP token."""
        return self.currency == "LP"


@dataclass
class ParsedField:
    """A parsed Paid or Receive field that may contain multiple assets."""

    raw: str
    assets: List[Asset]
    is_lp_format: bool = False


def _is_lp_data(field: str) -> bool:
    """Detect if a field contains LP data (multi-line format)."""
    if not field or not isinstance(field, str):
        return False
    if "\n" not in field:
        return False
    lines = [l.strip() for l in field.strip().split("\n") if l.strip()]
    if len(lines) != 2:
        return False
    pattern = r"^\d+\.?\d*\s+[A-Z]+$"
    return all(re.match(pattern, line) for line in lines)


def _parse_asset_line(line: str) -> Optional[Asset]:
    """Parse a single line like '263365360 ADA' or '57433 SNEK'."""
    line = line.strip()
    match = re.match(r"^(\d+\.?\d*)\s+([A-Z]+)$", line)
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        return Asset(amount=amount, currency=currency, raw=line)
    return None


def _parse_field(field: str) -> ParsedField:
    """Parse any Paid or Receive field (simple or LP format)."""
    if not field:
        return ParsedField(raw=field, assets=[], is_lp_format=False)

    raw = field.strip()

    # Check if LP format (multi-line with 2 assets)
    if _is_lp_data(field):
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        assets = [_parse_asset_line(l) for l in lines]
        assets = [a for a in assets if a is not None]
        return ParsedField(raw=raw, assets=assets, is_lp_format=True)

    # Simple format
    asset = _parse_asset_line(raw)
    if asset:
        return ParsedField(raw=raw, assets=[asset], is_lp_format=False)

    return ParsedField(raw=raw, assets=[], is_lp_format=False)


def _normalize_ada_amount(amount: float, currency: str) -> float:
    """Convert Lovelace to ADA if amount > 1,000,000."""
    if currency == "ADA" and amount > 1_000_000:
        return amount / 1_000_000
    return amount


def _load_minswap_csv(filepath: str) -> List[Dict]:
    """Load and parse the Minswap CSV file."""
    results = []

    with open(filepath, "r", encoding="utf-8") as f:
        csv_reader = reader(f)
        headers = next(csv_reader)

        for row in csv_reader:
            if len(row) < 11:
                continue

            row_dict = {
                "created_at": row[0],
                "created_tx": row[1],
                "protocol": row[2],
                "order_type": row[3],
                "status": row[4],
                "paid_raw": row[5],
                "receive_raw": row[6],
                "change_amount": row[7],
                "execution_fees": row[8],
                "executed_tx": row[9],
                "executed_at": row[10],
                "raw_data": ",".join(row),  # Store full row as raw_data
            }
            results.append(row_dict)

    return results


def _get_yoroi_tx_by_hash(yoroi_data: List[Dict], tx_hash: str) -> Optional[Dict]:
    """Find a Yoroi transaction by its hash."""
    for tx in yoroi_data:
        if tx.get("id") == tx_hash:
            return tx
    return None


def _extract_execution_fee(execution_fees_str: str) -> float:
    """Extract the fee amount from a string like '0.7 ADA'."""
    if not execution_fees_str:
        return 0.0
    match = re.match(r"([\d.]+)", execution_fees_str)
    if match:
        return float(match.group(1))
    return 0.0


def _create_swap_transactions(
    minswap_tx: Dict, yoroi_withdrawal: Dict, account_nickname: str, account_holder: str, plugin_name: str, result: List[AbstractTransaction]
) -> None:
    """
    Create InTransaction + OutTransaction for a Market/Limit swap.

    Tax treatment: Sell ADA (OutTransaction) + Buy Token (InTransaction)

    IMPORTANT: Use Yoroi's on-chain Sell Amount, not Minswap's Paid amount.
    This is because Yoroi reflects the actual on-chain transaction including
    the deposit return (Cardano's 2 ADA deposit for smart contracts).
    """
    created_tx = minswap_tx["created_tx"]
    executed_tx = minswap_tx["executed_tx"]
    timestamp = minswap_tx["created_at"]

    # Parse Minswap assets for output (what tokens were received)
    paid = _parse_field(minswap_tx["paid_raw"])
    receive = _parse_field(minswap_tx["receive_raw"])

    if not paid.assets or not receive.assets:
        return

    output_asset = receive.assets[0]

    # Get execution fee from Minswap
    execution_fee = _extract_execution_fee(minswap_tx["execution_fees"])

    # Get sell amount from Yoroi (the authoritative source for on-chain amounts)
    yoroi_sell_amount = 0.0
    if yoroi_withdrawal:
        sell_str = yoroi_withdrawal.get("sell_amount", "0")
        if sell_str:
            try:
                yoroi_sell_amount = float(sell_str)
            except (ValueError, TypeError):
                pass

    total_fee = execution_fee

    # CRITICAL: Use Yoroi's on-chain sell amount, not Minswap's Paid amount
    # Minswap's Paid excludes the 2 ADA deposit return, but Yoroi shows the full amount
    input_amount = yoroi_sell_amount
    input_currency = "ADA"  # Swaps always involve selling ADA

    # OutTransaction: Sell the input asset (ADA) using on-chain amount
    raw_data = f"Swap: {input_amount} {input_currency} -> {output_asset.amount} {output_asset.currency}"
    notes = f"Minswap {_get_operation_notes(minswap_tx['order_type'], paid, receive, input_amount)}"

    result.append(
        OutTransaction(
            plugin=plugin_name,
            unique_id=f"{created_tx[:16]}_swap_out",
            raw_data=raw_data,
            timestamp=timestamp,
            asset=input_currency,
            exchange=account_nickname,
            holder=account_holder,
            transaction_type=Keyword.SELL.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_out_no_fee=str(input_amount),
            crypto_fee=str(total_fee),
            notes=notes,
        )
    )

    # InTransaction: Buy the output asset (Token)
    # Cost basis = ADA given (including fees)
    cost_basis = input_amount + total_fee

    # Include derivation info for when direct price lookup fails
    # Format: DERIVE:<input_currency>:<input_amount_with_fees>
    # This allows deriving token price from the known ADA price
    derive_info = f"DERIVE:{input_currency}:{cost_basis}"
    notes_with_derive = f"{notes} | {derive_info}"

    result.append(
        InTransaction(
            plugin=plugin_name,
            unique_id=f"{created_tx[:16]}_swap_in",
            raw_data=raw_data,
            timestamp=timestamp,
            asset=output_asset.currency,
            exchange=account_nickname,
            holder=account_holder,
            transaction_type=Keyword.BUY.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_in=str(output_asset.amount),
            crypto_fee=str(execution_fee),
            notes=notes_with_derive,
        )
    )

    # Create one balancing Intra transaction for the deposit return
    # This balances the Yoroi Withdrawal entry (2 ADA deposit sent back)
    raw_data_minswap = minswap_tx.get("raw_data", "")

    result.append(
        IntraTransaction(
            plugin=plugin_name,
            unique_id=executed_tx,
            raw_data=raw_data_minswap,
            timestamp=timestamp,
            asset="ADA",
            from_exchange=account_nickname,
            from_holder=account_holder,
            to_exchange=Keyword.UNKNOWN.value,
            to_holder=Keyword.UNKNOWN.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_sent=str(_CARDANO_DEPOSIT_RETURN),
            crypto_received=Keyword.UNKNOWN.value,
            notes="Minswap Swap - deposit return",
        )
    )

    # Create second balancing Intra transaction for the ADA sent to the pool
    # This balances the Yoroi Withdrawal entry (the swap amount)
    # Received amount = input_amount (from minswap Paid) + deposit return + execution fee
    total_received = input_amount + _CARDANO_DEPOSIT_RETURN + execution_fee

    result.append(
        IntraTransaction(
            plugin=plugin_name,
            unique_id=created_tx,
            raw_data=raw_data_minswap,
            timestamp=timestamp,
            asset="ADA",
            from_exchange=Keyword.UNKNOWN.value,
            from_holder=Keyword.UNKNOWN.value,
            to_exchange=account_nickname,
            to_holder=account_holder,
            spot_price=Keyword.UNKNOWN.value,
            crypto_sent=Keyword.UNKNOWN.value,
            crypto_received=str(total_received),
            notes="Minswap Swap - ADA sent to contract",
        )
    )


def _create_lp_deposit_transactions(
    minswap_tx: Dict, yoroi_withdrawal: Dict, account_nickname: str, account_holder: str, plugin_name: str, result: List[AbstractTransaction]
) -> None:
    """
    Create transactions for LP Deposit.

    Tax treatment: Depositing assets into an LP pool is a taxable event.
    You are "selling" your assets (ADA + token) to receive LP tokens.
    The cost basis of the LP tokens equals the value of assets deposited.
    """
    created_tx = minswap_tx["created_tx"]
    timestamp = minswap_tx["created_at"]

    # Parse assets
    paid = _parse_field(minswap_tx["paid_raw"])
    receive = _parse_field(minswap_tx["receive_raw"])

    if not paid.assets or not receive.assets:
        return

    lp_token = receive.assets[0]

    # Extract ADA and token amounts
    ada_amount = 0.0
    token_amount = 0.0
    token_currency = None
    ada_asset = None

    for asset in paid.assets:
        if asset.currency == "ADA":
            ada_amount = _normalize_ada_amount(asset.amount, asset.currency)
            ada_asset = asset
        else:
            token_amount = asset.amount
            token_currency = asset.currency

    # Determine LP pair
    lp_pair = f"ADA-{token_currency}" if token_currency else "ADA-unknown"
    lp_asset_name = f"LP-{lp_pair}"

    # Store cost basis for later LP removal
    # Key must include both pool AND LP amount to avoid collisions between different pools
    lp_key = f"{lp_pair}_{int(lp_token.amount)}"
    _LP_COST_BASES[lp_key] = {
        "ada_cost": ada_amount,
        "token_cost": token_amount,
        "token_currency": token_currency,
        "timestamp": timestamp,
        "pool": lp_pair,
        "deposit_tx": created_tx,
    }

    # Create OUT transactions for each asset deposited
    # These represent "selling" the assets to receive LP tokens

    # OUT transaction for ADA
    if ada_amount > 0:
        raw_data_ada = f"LP Deposit: {ada_amount} ADA to {lp_pair} pool -> {lp_token.amount} LP"
        notes_ada = f"Minswap LP Deposit to {lp_pair} pool - ADA portion"
        result.append(
            OutTransaction(
                plugin=plugin_name,
                unique_id=f"{created_tx[:16]}_lp_deposit_ada",
                raw_data=raw_data_ada,
                timestamp=timestamp,
                asset="ADA",
                exchange=account_nickname,
                holder=account_holder,
                transaction_type=Keyword.SELL.value,
                spot_price=Keyword.UNKNOWN.value,
                crypto_out_no_fee=str(ada_amount),
                crypto_fee="0",
                notes=notes_ada,
            )
        )

    # OUT transaction for the token (e.g., SNEK)
    if token_amount > 0 and token_currency:
        raw_data_token = f"LP Deposit: {token_amount} {token_currency} to {lp_pair} pool -> {lp_token.amount} LP"
        # Include derivation info so price can be derived from ADA
        derive_info = f"DERIVE:ADA:{ada_amount}"
        notes_token = f"Minswap LP Deposit to {lp_pair} pool - {token_currency} portion | {derive_info}"
        result.append(
            OutTransaction(
                plugin=plugin_name,
                unique_id=f"{created_tx[:16]}_lp_deposit_{token_currency.lower()}",
                raw_data=raw_data_token,
                timestamp=timestamp,
                asset=token_currency,
                exchange=account_nickname,
                holder=account_holder,
                transaction_type=Keyword.SELL.value,
                spot_price=Keyword.UNKNOWN.value,
                crypto_out_no_fee=str(token_amount),
                crypto_fee="0",
                notes=notes_token,
            )
        )

    # IN transaction for LP tokens received
    # Cost basis = value of assets deposited (stored for later use)
    raw_data_lp = f"LP Deposit: {ada_amount} ADA + {token_amount} {token_currency} -> {lp_token.amount} LP"
    # Include derivation info: double the ADA contribution for spot price calculation
    derive_info = f"DERIVE:ADA:{ada_amount * 2}"
    notes_lp = f"Minswap LP Deposit to {lp_pair} pool - received LP tokens | Cost basis: {ada_amount} ADA + {token_amount} {token_currency} | {derive_info}"
    result.append(
        InTransaction(
            plugin=plugin_name,
            unique_id=f"{created_tx[:16]}_lp_deposit_in",
            raw_data=raw_data_lp,
            timestamp=timestamp,
            asset=lp_asset_name,
            exchange=account_nickname,
            holder=account_holder,
            transaction_type=Keyword.BUY.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_in=str(lp_token.amount),
            crypto_fee="0",
            notes=notes_lp,
        )
    )

    # Create two balancing Intra transactions to replace/complement the Yoroi entries
    # Get execution fee and executed tx from minswap
    execution_fee = _extract_execution_fee(minswap_tx["execution_fees"])
    executed_tx = minswap_tx["executed_tx"]

    # Build raw_data from minswap row
    raw_data_minswap = minswap_tx.get("raw_data", "")

    # Total ADA sent = paid ADA + deposit return (2.0) + execution fee
    # Note: ada_amount is already normalized from Lovelace
    total_ada_sent = ada_amount + _CARDANO_DEPOSIT_RETURN + execution_fee

    # Balancing Intra 1: The deposit return (from Yoroi "receive" row)
    # Direction: andrew_wallet -> __unknown (sending 2 ADA deposit back)
    result.append(
        IntraTransaction(
            plugin=plugin_name,
            unique_id=executed_tx,
            raw_data=raw_data_minswap,
            timestamp=timestamp,
            asset="ADA",
            from_exchange=account_nickname,
            from_holder=account_holder,
            to_exchange=Keyword.UNKNOWN.value,
            to_holder=Keyword.UNKNOWN.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_sent=str(_CARDANO_DEPOSIT_RETURN),
            crypto_received=Keyword.UNKNOWN.value,
            notes="Minswap LP Deposit - deposit return",
        )
    )

    # Balancing Intra 2: The ADA sent to the pool (from Yoroi "send" row)
    # Direction: __unknown -> andrew_wallet (receiving the ADA back from the pool operation)
    result.append(
        IntraTransaction(
            plugin=plugin_name,
            unique_id=created_tx,
            raw_data=raw_data_minswap,
            timestamp=timestamp,
            asset="ADA",
            from_exchange=Keyword.UNKNOWN.value,
            from_holder=Keyword.UNKNOWN.value,
            to_exchange=account_nickname,
            to_holder=account_holder,
            spot_price=Keyword.UNKNOWN.value,
            crypto_sent=Keyword.UNKNOWN.value,
            crypto_received=str(total_ada_sent),
            notes="Minswap LP Deposit - ADA sent to pool",
        )
    )


def _create_zap_out_transactions(
    minswap_tx: Dict, yoroi_withdrawal: Dict, account_nickname: str, account_holder: str, plugin_name: str, result: List[AbstractTransaction]
) -> None:
    """
    Create InTransaction + OutTransaction for Zap Out (LP removal).

    Tax treatment: Sell LP tokens (OutTransaction) + Buy ADA (InTransaction)
    Gain/Loss = ADA received - cost basis of LP
    """
    created_tx = minswap_tx["created_tx"]
    executed_tx = minswap_tx["executed_tx"]
    timestamp = minswap_tx["created_at"]

    # Parse assets
    paid = _parse_field(minswap_tx["paid_raw"])
    receive = _parse_field(minswap_tx["receive_raw"])

    if not paid.assets or not receive.assets:
        return

    lp_token = paid.assets[0]
    ada_received = receive.assets[0]

    # Get execution fee
    execution_fee = _extract_execution_fee(minswap_tx["execution_fees"])

    total_fee = execution_fee

    # Look up cost basis for this LP amount
    # First, try to find by matching LP token amount (most reliable)
    cost_basis = {"ada_cost": 0.0, "token_cost": 0.0, "token_currency": "UNKNOWN", "pool": "unknown"}
    lp_amount = int(lp_token.amount)

    for key, cb in _LP_COST_BASES.items():
        # Key format is poolname_amount, extract amount
        key_amount = int(key.split('_')[-1])
        if key_amount == lp_amount:
            cost_basis = cb
            break

    # If not found by amount, try the old method (pool from received assets)
    if cost_basis.get("pool") == "unknown":
        pool_name = "unknown"
        for asset in receive.assets:
            if asset.currency != "LP":
                pool_name = f"ADA-{asset.currency}"
                break
        lp_key = f"{pool_name}_{lp_amount}"
        cost_basis = _LP_COST_BASES.get(lp_key, cost_basis)

    # Calculate gain/loss
    net_proceeds = ada_received.amount - total_fee
    cost_basis_ada = cost_basis.get("ada_cost", 0.0)
    gain_loss = net_proceeds - cost_basis_ada

    # Determine pool name (e.g., ADA-MIN, ADA-SNEK)
    pool_name = cost_basis.get("pool", "unknown")
    lp_asset_name = f"LP-{pool_name}"  # Specific LP token name like LP-ADA-MIN

    raw_data = f"Zap Out: {lp_token.amount} {lp_asset_name} -> {ada_received.amount} ADA"
    notes = f"Minswap LP Removal from {pool_name} pool - Gain/Loss: {gain_loss:.2f} ADA"

    # OutTransaction: Remove/sell LP tokens
    result.append(
        OutTransaction(
            plugin=plugin_name,
            unique_id=f"{created_tx[:16]}_lp_remove_out",
            raw_data=raw_data,
            timestamp=timestamp,
            asset=lp_asset_name,
            exchange=account_nickname,
            holder=account_holder,
            transaction_type=Keyword.SELL.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_out_no_fee=str(lp_token.amount),
            crypto_fee="0",
            notes=notes,
        )
    )

    # Note: We do NOT create a separate OUT transaction for the original token (e.g., SNEK)
    # because the ADA IN already represents both the original ADA and the token value.
    # The token was effectively "sold" at deposit time when LP tokens were received.
    # The gain/loss is calculated on the LP token disposal (LP OUT vs LP IN cost basis).

    # InTransaction: Receive ADA (includes both original ADA + token value converted to ADA)
    result.append(
        InTransaction(
            plugin=plugin_name,
            unique_id=f"{created_tx[:16]}_lp_remove_in",
            raw_data=raw_data,
            timestamp=timestamp,
            asset="ADA",
            exchange=account_nickname,
            holder=account_holder,
            transaction_type=Keyword.BUY.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_in=str(ada_received.amount),
            crypto_fee=str(total_fee),
            notes=notes,
        )
    )

    # Create one balancing Intra transaction for the deposit return
    # This balances the Yoroi Withdrawal entry (2 ADA deposit sent back)
    raw_data_minswap = minswap_tx.get("raw_data", "")

    result.append(
        IntraTransaction(
            plugin=plugin_name,
            unique_id=executed_tx,
            raw_data=raw_data_minswap,
            timestamp=timestamp,
            asset="ADA",
            from_exchange=account_nickname,
            from_holder=account_holder,
            to_exchange=Keyword.UNKNOWN.value,
            to_holder=Keyword.UNKNOWN.value,
            spot_price=Keyword.UNKNOWN.value,
            crypto_sent=str(_CARDANO_DEPOSIT_RETURN),
            crypto_received=Keyword.UNKNOWN.value,
            notes="Minswap LP Removal - deposit return",
        )
    )


def _get_operation_notes(order_type: str, paid: ParsedField, receive: ParsedField, input_amount: Optional[float] = None) -> str:
    """Get human-readable notes for an operation.

    Args:
        order_type: The Minswap order type (Market, Limit, Zap Out, Deposit)
        paid: Parsed paid assets
        receive: Parsed received assets
        input_amount: Optional actual input amount (use Yoroi's on-chain amount for swaps)
    """
    if order_type in [_ORDER_TYPE_MARKET, _ORDER_TYPE_LIMIT]:
        if paid.assets and receive.assets:
            # Use the actual on-chain amount (from Yoroi) if provided, otherwise use Minswap's amount
            amount_display = input_amount if input_amount is not None else paid.assets[0].amount
            return f"swap {amount_display} {paid.assets[0].currency} for {receive.assets[0].amount} {receive.assets[0].currency}"
    elif order_type == _ORDER_TYPE_ZAP_OUT:
        if paid.assets and receive.assets:
            return f"LP removal: {paid.assets[0].amount} LP -> {receive.assets[0].amount} {receive.assets[0].currency}"
    elif order_type == _ORDER_TYPE_DEPOSIT:
        if paid.assets and receive.assets:
            asset_strs = [f"{a.amount} {a.currency}" for a in paid.assets]
            return f"LP deposit: {' + '.join(asset_strs)} -> {receive.assets[0].amount} LP"
    return f"operation: {order_type}"


class InputPlugin(AbstractInputPlugin):
    __YOROI: str = "Yoroi"
    __MINSWAP_PLUGIN: str = "Yoroi+Minswap"

    __TYPE_INDEX: int = 0
    __DATETIME_INDEX: int = 10
    __TRANSACTION_ID_INDEX: int = 11
    __FEE_INDEX: int = 5
    __FEE_CURRENCY_INDEX: int = 6
    __BUY_AMOUNT_INDEX: int = 1
    __BUY_CURRENCY_INDEX: int = 2
    __SELL_AMOUNT_INDEX: int = 3
    __SELL_CURRENCY_INDEX: int = 4
    __COMMENT_INDEX: int = 9

    __DELIMITER = ","

    def __init__(
        self,
        account_holder: str,
        account_nickname: str,
        csv_file: str,
        timezone: str,
        native_fiat: Optional[str] = None,
        minswap_csv: Optional[str] = None,
    ) -> None:
        super().__init__(account_holder=account_holder, native_fiat=native_fiat)
        self.__account_nickname: str = account_nickname
        self.__csv_file: str = csv_file
        self.__minswap_csv: Optional[str] = minswap_csv
        self.__timezone = pytz.timezone(timezone)

        self.__logger: logging.Logger = create_logger(f"{self.__YOROI}/{self.__account_nickname}/{self.account_holder}")

    def load(self, country: AbstractCountry) -> List[AbstractTransaction]:
        result: List[AbstractTransaction] = []

        # Load Yoroi data
        yoroi_data = self._load_yoroi_csv()

        # Process basic Yoroi transactions (Deposits/Withdrawals/Staking)
        self._process_yoroi_transactions(yoroi_data, result)

        # Process Minswap transactions if CSV provided
        if self.__minswap_csv:
            self._process_minswap_transactions(yoroi_data, result)

        return result

    def _load_yoroi_csv(self) -> List[Dict]:
        """Load Yoroi CSV and return as list of dicts."""
        yoroi_data = []

        with open(self.__csv_file, encoding="utf-8") as csv_file:
            lines = reader(csv_file, delimiter=self.__DELIMITER)
            header_found = False
            for line in lines:
                if not header_found:
                    header_found = True
                    continue

                if len(line) < 12:
                    continue

                tx = {
                    "type": line[self.__TYPE_INDEX],
                    "buy_amount": line[self.__BUY_AMOUNT_INDEX],
                    "buy_currency": line[self.__BUY_CURRENCY_INDEX],
                    "sell_amount": line[self.__SELL_AMOUNT_INDEX],
                    "sell_currency": line[self.__SELL_CURRENCY_INDEX],
                    "fee": line[self.__FEE_INDEX],
                    "fee_currency": line[self.__FEE_CURRENCY_INDEX],
                    "comment": line[self.__COMMENT_INDEX] if len(line) > self.__COMMENT_INDEX else "",
                    "date": line[self.__DATETIME_INDEX],
                    "id": line[self.__TRANSACTION_ID_INDEX] if line[self.__TRANSACTION_ID_INDEX] else "",
                }
                yoroi_data.append(tx)

        return yoroi_data

    def _process_yoroi_transactions(self, yoroi_data: List[Dict], result: List[AbstractTransaction]) -> None:
        """Process Yoroi transactions into DaLI transactions."""
        for line in yoroi_data:
            raw_data = self.__DELIMITER.join(
                [
                    line["type"],
                    line["buy_amount"],
                    line["buy_currency"],
                    line["sell_amount"],
                    line["sell_currency"],
                    line["fee"],
                    line["fee_currency"],
                    "",
                    "",
                    line["comment"],
                    line["date"],
                    line["id"],
                ]
            )

            try:
                timestamp_value = parse(line["date"])
                timestamp_value = self.__timezone.normalize(self.__timezone.localize(timestamp_value))
            except Exception:
                timestamp_value = datetime.now()

            transaction_type = line["type"]
            spot_price = Keyword.UNKNOWN.value
            crypto_hash = line["id"] if line["id"] else Keyword.UNKNOWN.value
            currency = None

            if transaction_type == _RECV:
                currency = line["buy_currency"]
                amount_number = RP2Decimal(line["buy_amount"]) if line["buy_amount"] else ZERO
            elif transaction_type == _SENT:
                currency = line["sell_currency"]
                amount_number = RP2Decimal(line["sell_amount"]) if line["sell_amount"] else ZERO
            else:
                self.__logger.error("Unsupported transaction type: %s", transaction_type)
                continue

            fee_currency = line["fee_currency"] if line["fee_currency"] else None
            if fee_currency and fee_currency == currency and line["fee"]:
                fee_number = RP2Decimal(line["fee"])
            else:
                fee_number = ZERO

            if amount_number == ZERO and fee_number > ZERO:
                self.__logger.warning("Possible dusting attack, skipping: %s", raw_data)
                continue

            # Check for staking rewards
            comment = line.get("comment", "")
            is_staking_reward = transaction_type == _RECV and "Staking Reward" in comment

            if is_staking_reward:
                result.append(
                    InTransaction(
                        plugin=self.__YOROI,
                        unique_id=crypto_hash,
                        raw_data=raw_data,
                        timestamp=f"{timestamp_value}",
                        asset=currency,
                        exchange=self.__account_nickname,
                        holder=self.account_holder,
                        transaction_type=Keyword.STAKING.value,
                        spot_price=spot_price,
                        crypto_in=str(amount_number),
                        notes=comment,
                    )
                )
            elif transaction_type in {_RECV, _SENT}:
                result.append(
                    IntraTransaction(
                        plugin=self.__YOROI,
                        unique_id=crypto_hash,
                        raw_data=raw_data,
                        timestamp=f"{timestamp_value}",
                        asset=currency,
                        from_exchange=self.__account_nickname if transaction_type == _SENT else Keyword.UNKNOWN.value,
                        from_holder=self.account_holder if transaction_type == _SENT else Keyword.UNKNOWN.value,
                        to_exchange=self.__account_nickname if transaction_type == _RECV else Keyword.UNKNOWN.value,
                        to_holder=self.account_holder if transaction_type == _RECV else Keyword.UNKNOWN.value,
                        spot_price=spot_price,
                        crypto_sent=str(amount_number + fee_number) if transaction_type == _SENT else Keyword.UNKNOWN.value,
                        crypto_received=str(amount_number) if transaction_type == _RECV else Keyword.UNKNOWN.value,
                        notes=None,
                    )
                )

    def _process_minswap_transactions(self, yoroi_data: List[Dict], result: List[AbstractTransaction]) -> None:
        """Process Minswap transactions into proper InTransaction/OutTransaction pairs."""
        try:
            minswap_txs = _load_minswap_csv(self.__minswap_csv)
        except FileNotFoundError:
            self.__logger.warning("Minswap CSV not found: %s", self.__minswap_csv)
            return

        self.__logger.info("Processing %d Minswap transactions", len(minswap_txs))

        # First pass: process all Minswap transactions
        # Note: We need to process LP Deposits BEFORE Zap Outs to have cost basis available
        # So split into two passes

        # First pass: LP Deposits (order_type = 'Deposit')
        for minswap_tx in minswap_txs:
            if minswap_tx["order_type"] == _ORDER_TYPE_DEPOSIT:
                # Find matching Yoroi withdrawal
                yoroi_withdrawal = _get_yoroi_tx_by_hash(yoroi_data, minswap_tx["created_tx"])
                _create_lp_deposit_transactions(minswap_tx, yoroi_withdrawal, self.__account_nickname, self.account_holder, self.__MINSWAP_PLUGIN, result)

        # Second pass: Swaps (Market, Limit)
        for minswap_tx in minswap_txs:
            if minswap_tx["order_type"] in [_ORDER_TYPE_MARKET, _ORDER_TYPE_LIMIT]:
                yoroi_withdrawal = _get_yoroi_tx_by_hash(yoroi_data, minswap_tx["created_tx"])
                _create_swap_transactions(minswap_tx, yoroi_withdrawal, self.__account_nickname, self.account_holder, self.__MINSWAP_PLUGIN, result)

        # Third pass: LP Removals (Zap Out)
        for minswap_tx in minswap_txs:
            if minswap_tx["order_type"] == _ORDER_TYPE_ZAP_OUT:
                yoroi_withdrawal = _get_yoroi_tx_by_hash(yoroi_data, minswap_tx["created_tx"])
                _create_zap_out_transactions(minswap_tx, yoroi_withdrawal, self.__account_nickname, self.account_holder, self.__MINSWAP_PLUGIN, result)

        self.__logger.info(
            "Minswap processed: %d swaps, %d LP deposits, %d LP removals",
            sum(1 for tx in minswap_txs if tx["order_type"] in [_ORDER_TYPE_MARKET, _ORDER_TYPE_LIMIT]),
            sum(1 for tx in minswap_txs if tx["order_type"] == _ORDER_TYPE_DEPOSIT),
            sum(1 for tx in minswap_txs if tx["order_type"] == _ORDER_TYPE_ZAP_OUT),
        )
