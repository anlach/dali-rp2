# Copyright 2025 randumari
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

# Taostats REST plugin links:
# API Documentation: https://docs.taostats.io/docs/the-taostats-api
# Endpoint: https://api.taostats.io
# Authentication: Authorization header with API key

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bittensor
import requests
from rp2.abstract_country import AbstractCountry
from rp2.logger import create_logger
from rp2.rp2_decimal import RP2Decimal

from dali.abstract_input_plugin import AbstractInputPlugin
from dali.abstract_transaction import AbstractTransaction
from dali.configuration import Keyword
from dali.in_transaction import InTransaction
from dali.intra_transaction import IntraTransaction
from dali.out_transaction import OutTransaction

# keywords
_ACTION: str = "action"
_ALPHA: str = "alpha"
_AMOUNT: str = "amount"
_COLDKEY: str = "coldkey"
_DELEGATE: str = "DELEGATE"
_EXTRINSIC_ID: str = "extrinsic_id"
_FEE: str = "fee"
_NETUID: str = "netuid"
_TIMESTAMP: str = "timestamp"
_UNDELEGATE: str = "UNDELEGATE"
_USD: str = "usd"

# Constants
_ROOT_SUBNET_NETUID: int = 0
_TAO_DECIMALS: int = 9
_ALPHA_DECIMALS: int = 9
_API_BASE_URL: str = "https://api.taostats.io/api"
_BLOCKS_PER_DAY: int = 1_036_800  # ~12 blocks/second
_CURRENT_BLOCK: int = 7_800_000  # Approximate current block number


class InputPlugin(AbstractInputPlugin):
    __PLUGIN_NAME: str = "taostats_REST"

    def __init__(
        self,
        account_holder: str,
        api_key: str,
        coldkey: Optional[str] = None,
        subtensor_network: str = "archive",
        include_emissions: bool = True,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        native_fiat: Optional[str] = None,
    ) -> None:
        super().__init__(account_holder=account_holder, native_fiat=native_fiat)
        self.__api_key: str = api_key
        self.__coldkey: str = coldkey if coldkey else account_holder
        self.__subtensor_network: str = subtensor_network
        self.__include_emissions: bool = include_emissions
        self.__start_date: Optional[str] = start_date
        self.__end_date: Optional[str] = end_date
        self.__logger: logging.Logger = create_logger(f"{self.__PLUGIN_NAME}/{self.account_holder}")

    def cache_key(self) -> Optional[str]:
        return f"taostats-{self.account_holder}"

    def _calculate_block_for_date(self, date_str: str) -> int:
        """Calculate estimated block number for a given date.

        Uses current block ~7.8M and works backwards at ~12 blocks/second.
        """
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)

            # Calculate days difference
            days_diff = (now - target_date).days

            if days_diff < 0:
                self.__logger.warning(f"Date {date_str} is in the future, using current block")
                return _CURRENT_BLOCK

            # Calculate approximate block number
            estimated_block = _CURRENT_BLOCK - (days_diff * _BLOCKS_PER_DAY)

            self.__logger.debug(f"Estimated block for {date_str}: {estimated_block} (days_diff={days_diff})")
            return max(0, estimated_block)

        except ValueError as e:
            self.__logger.error(f"Invalid date format {date_str}: {e}")
            return _CURRENT_BLOCK

    def _get_date_range(self) -> List[str]:
        """Get list of dates between start_date and end_date."""
        if not self.__start_date or not self.__end_date:
            return []

        try:
            start = datetime.strptime(self.__start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(self.__end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            dates = []
            current = start
            while current <= end:
                dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)

            return dates
        except ValueError as e:
            self.__logger.error(f"Invalid date range: {e}")
            return []

    def load(self, country: AbstractCountry) -> List[AbstractTransaction]:
        result: List[AbstractTransaction] = []
        delegations: List[Dict[str, Any]] = self._fetch_delegations()

        for delegation in delegations:
            transactions = self._process_delegation(delegation)
            result.extend(transactions)

        # Fetch emissions if enabled
        if self.__include_emissions:
            # Check for historical backfilling
            date_range = self._get_date_range()

            if date_range:
                # Historical backfilling mode
                self.__logger.info(f"Starting historical emission backfilling for {len(date_range)} days")
                total_emissions = 0

                for date_str in date_range:
                    block_num = self._calculate_block_for_date(date_str)
                    self.__logger.info(f"Fetching emissions for {date_str} at block {block_num}")

                    try:
                        emissions: List[Dict[str, Any]] = self._fetch_emissions(block=block_num)
                        for emission in emissions:
                            transactions = self._process_emission(emission, date_str)
                            result.extend(transactions)
                            total_emissions += 1

                        self.__logger.debug(f"Processed {len(emissions)} emissions for {date_str}")

                    except Exception as e:
                        self.__logger.warning(f"Failed to fetch emissions for {date_str}: {e}")
                        continue

                self.__logger.info(f"Historical backfilling complete: {total_emissions} emission records from {len(date_range)} days")
            else:
                # Current emissions only (existing behavior)
                emissions: List[Dict[str, Any]] = self._fetch_emissions()
                for emission in emissions:
                    transactions = self._process_emission(emission)
                    result.extend(transactions)

        self.__logger.info(f"Loaded {len(result)} transactions from Taostats for {self.account_holder}")
        return result

    def _fetch_delegations(self) -> List[Dict[str, Any]]:
        """Fetch delegation history from Taostats API."""
        url = f"{_API_BASE_URL}/delegation/v1"
        headers = {
            "Authorization": self.__api_key,
            "Content-Type": "application/json",
        }
        params = {
            "nominator": self.__coldkey,
        }

        self.__logger.debug(f"Fetching delegations from {url} with params {params}")

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Handle the response structure - likely { "data": [...] } or direct list
            if isinstance(data, dict):
                if "data" in data:
                    return data["data"]
                elif "result" in data:
                    return data["result"]
                else:
                    self.__logger.warning(f"Unexpected response structure: {data.keys()}")
                    return []
            elif isinstance(data, list):
                return data
            else:
                self.__logger.warning(f"Unexpected response type: {type(data)}")
                return []

        except requests.exceptions.HTTPError as e:
            self.__logger.error(f"HTTP error fetching delegations: {e}")
            if e.response is not None:
                self.__logger.error(f"Response body: {e.response.text}")
            return []
        except requests.exceptions.RequestException as e:
            self.__logger.error(f"Request error fetching delegations: {e}")
            return []
        except json.JSONDecodeError as e:
            self.__logger.error(f"JSON decode error: {e}")
            return []

    def _fetch_emissions(self, block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch emission (staking rewards) data from Bittensor Subtensor API.

        Args:
            block: Optional block number for historical queries. If None, fetches current emissions.
        """
        block_info = f" at block {block}" if block else " (current)"
        self.__logger.debug(f"Fetching emissions for coldkey {self.__coldkey} from subtensor network {self.__subtensor_network}{block_info}")

        try:
            # Connect to subtensor
            subtensor = bittensor.Subtensor(network=self.__subtensor_network)

            # Get stake info for the coldkey (optionally at historical block)
            if block is not None:
                stake_info = subtensor.get_stake_info_for_coldkey(self.__coldkey, block=block)
            else:
                stake_info = subtensor.get_stake_info_for_coldkey(self.__coldkey)

            # Convert StakeInfo objects to dicts with relevant emission data
            emissions: List[Dict[str, Any]] = []
            for stake in stake_info:
                # Each stake has hotkey_ss58, netuid, stake, and emission (as Balance)
                emission_rao = stake.emission.rao if stake.emission else 0
                if emission_rao > 0:
                    emissions.append({
                        "hotkey": stake.hotkey_ss58,
                        "netuid": stake.netuid,
                        "emission_rao": str(emission_rao),
                        "stake_rao": str(stake.stake.rao) if stake.stake else "0",
                    })

            self.__logger.debug(f"Found {len(emissions)} emission entries")
            return emissions

        except Exception as e:
            self.__logger.error(f"Error fetching emissions from subtensor: {e}")
            return []

    def _process_emission(self, emission: Dict[str, Any], date_str: Optional[str] = None) -> List[AbstractTransaction]:
        """Process a single emission record into an InTransaction.

        Args:
            emission: The emission data dictionary
            date_str: Optional date string (YYYY-MM-DD) for historical data. If None, uses current date.
        """
        transactions: List[AbstractTransaction] = []

        hotkey = emission.get("hotkey", "")
        netuid = emission.get("netuid", 0)
        emission_rao = emission.get("emission_rao", "0")

        # Convert RAO to TAO
        emission_tao = self._rao_to_tao(emission_rao)

        # Skip zero emissions
        if emission_tao == "0" or RP2Decimal(emission_tao) <= RP2Decimal("0"):
            return transactions

        # Use provided date or current date for unique ID
        date = date_str if date_str else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        unique_id = f"emission-{netuid}-{hotkey}-{date}"

        # Get timestamp for the transaction
        timestamp = datetime.now(timezone.utc).isoformat()

        in_tx = InTransaction(
            plugin=self.__PLUGIN_NAME,
            unique_id=unique_id,
            raw_data=json.dumps(emission),
            timestamp=timestamp,
            asset="TAO",
            exchange="Staking",
            holder=self.account_holder,
            transaction_type=Keyword.STAKING.value,
            spot_price="0",  # Will be filled in by price lookups later
            crypto_in=emission_tao,
            notes=f"Daily staking emission for subnet {netuid} from {hotkey}",
            is_spot_price_from_web=False,
            fiat_ticker=self.native_fiat,
        )
        transactions.append(in_tx)

        return transactions

    def _process_delegation(self, delegation: Dict[str, Any]) -> List[AbstractTransaction]:
        """Process a single delegation/undelegation record into transactions."""
        transactions: List[AbstractTransaction] = []

        action = delegation.get(_ACTION, "")
        netuid = delegation.get(_NETUID, _ROOT_SUBNET_NETUID)
        timestamp = delegation.get(_TIMESTAMP, "")
        amount_tao = delegation.get(_AMOUNT, "0")
        alpha = delegation.get(_ALPHA, "0")
        usd_value = delegation.get(_USD, "0")
        fee = delegation.get(_FEE, "0")
        extrinsic_id = delegation.get(_EXTRINSIC_ID, "")

        # Convert timestamp to ISO format if needed
        timestamp = self._normalize_timestamp(timestamp)

        # Convert amounts from RAO (10^-9 TAO) to TAO
        amount_tao = self._rao_to_tao(amount_tao)
        alpha = self._rao_to_tao(alpha)
        usd_value = RP2Decimal(usd_value) if usd_value else RP2Decimal("0")
        fee = self._rao_to_tao(fee)

        # Calculate spot price if we have USD value
        spot_price = "0"
        amount_tao_decimal = RP2Decimal(amount_tao)
        zero = RP2Decimal("0")
        if amount_tao and amount_tao_decimal > zero:
            spot_price = str(usd_value / RP2Decimal(amount_tao))

        unique_id = f"{extrinsic_id}_{action}_{netuid}"
        raw_data = json.dumps(delegation)

        if action == _DELEGATE:
            transactions.extend(
                self._process_delegate(
                    timestamp=timestamp,
                    netuid=netuid,
                    amount_tao=amount_tao,
                    alpha=alpha,
                    spot_price=spot_price,
                    usd_value=str(usd_value),
                    fee=fee,
                    unique_id=unique_id,
                    raw_data=raw_data,
                )
            )
        elif action == _UNDELEGATE:
            transactions.extend(
                self._process_undelegate(
                    timestamp=timestamp,
                    netuid=netuid,
                    amount_tao=amount_tao,
                    alpha=alpha,
                    spot_price=spot_price,
                    usd_value=str(usd_value),
                    fee=fee,
                    unique_id=unique_id,
                    raw_data=raw_data,
                )
            )
        else:
            self.__logger.warning(f"Unknown action: {action}")

        return transactions

    def _process_delegate(
        self,
        timestamp: str,
        netuid: int,
        amount_tao: str,
        alpha: str,
        spot_price: str,
        usd_value: str,
        fee: str,
        unique_id: str,
        raw_data: str,
    ) -> List[AbstractTransaction]:
        """Process a DELEGATE (staking) action."""
        transactions: List[AbstractTransaction] = []

        if netuid == _ROOT_SUBNET_NETUID:
            # Root subnet staking: INTRA transaction
            intra = IntraTransaction(
                plugin=self.__PLUGIN_NAME,
                unique_id=unique_id,
                raw_data=raw_data,
                timestamp=timestamp,
                asset="TAO",
                from_exchange="Wallet",
                from_holder=self.account_holder,
                to_exchange="Staking",
                to_holder=self.account_holder,
                spot_price=spot_price,
                crypto_sent=amount_tao,
                crypto_received=amount_tao,
                notes=f"Root subnet staking (netuid {netuid})",
                is_spot_price_from_web=False,
                fiat_ticker=self.native_fiat,
            )
            transactions.append(intra)
        else:
            # Non-root subnet staking: OUT (TAO) + IN (alpha token)
            alpha_asset = self._get_alpha_asset_name(netuid)

            # OUT transaction for TAO spent
            out_tx = OutTransaction(
                plugin=self.__PLUGIN_NAME,
                unique_id=f"{unique_id}_out",
                raw_data=raw_data,
                timestamp=timestamp,
                asset="TAO",
                exchange="Staking",
                holder=self.account_holder,
                transaction_type=Keyword.SELL.value,
                spot_price=spot_price,
                crypto_out_no_fee=amount_tao,
                crypto_fee=fee,
                notes=f"Staking on subnet {netuid}",
                is_spot_price_from_web=False,
                fiat_ticker=self.native_fiat,
            )
            transactions.append(out_tx)

            # IN transaction for alpha tokens received
            in_tx = InTransaction(
                plugin=self.__PLUGIN_NAME,
                unique_id=f"{unique_id}_in",
                raw_data=raw_data,
                timestamp=timestamp,
                asset=alpha_asset,
                exchange="Staking",
                holder=self.account_holder,
                transaction_type=Keyword.STAKING.value,
                spot_price="0",  # Alpha tokens don't have direct USD value in the API
                crypto_in=alpha,
                notes=f"Received from staking on subnet {netuid}",
                is_spot_price_from_web=False,
                fiat_ticker=self.native_fiat,
            )
            transactions.append(in_tx)

        return transactions

    def _process_undelegate(
        self,
        timestamp: str,
        netuid: int,
        amount_tao: str,
        alpha: str,
        spot_price: str,
        usd_value: str,
        fee: str,
        unique_id: str,
        raw_data: str,
    ) -> List[AbstractTransaction]:
        """Process an UNDELEGATE (unstaking) action."""
        transactions: List[AbstractTransaction] = []

        if netuid == _ROOT_SUBNET_NETUID:
            # Root subnet unstaking: INTRA transaction
            intra = IntraTransaction(
                plugin=self.__PLUGIN_NAME,
                unique_id=unique_id,
                raw_data=raw_data,
                timestamp=timestamp,
                asset="TAO",
                from_exchange="Staking",
                from_holder=self.account_holder,
                to_exchange="Wallet",
                to_holder=self.account_holder,
                spot_price=spot_price,
                crypto_sent=amount_tao,
                crypto_received=amount_tao,
                notes=f"Root subnet unstaking (netuid {netuid})",
                is_spot_price_from_web=False,
                fiat_ticker=self.native_fiat,
            )
            transactions.append(intra)
        else:
            # Non-root subnet unstaking: OUT (alpha token) + IN (TAO)
            alpha_asset = self._get_alpha_asset_name(netuid)

            # OUT transaction for alpha tokens returned
            out_tx = OutTransaction(
                plugin=self.__PLUGIN_NAME,
                unique_id=f"{unique_id}_out",
                raw_data=raw_data,
                timestamp=timestamp,
                asset=alpha_asset,
                exchange="Staking",
                holder=self.account_holder,
                transaction_type=Keyword.SELL.value,
                spot_price="0",  # Alpha doesn't have direct USD
                crypto_out_no_fee=alpha,
                crypto_fee="0",
                notes=f"Returned from unstaking subnet {netuid}",
                is_spot_price_from_web=False,
                fiat_ticker=self.native_fiat,
            )
            transactions.append(out_tx)

            # IN transaction for TAO received
            in_tx = InTransaction(
                plugin=self.__PLUGIN_NAME,
                unique_id=f"{unique_id}_in",
                raw_data=raw_data,
                timestamp=timestamp,
                asset="TAO",
                exchange="Staking",
                holder=self.account_holder,
                transaction_type=Keyword.SELL.value,
                spot_price=spot_price,
                crypto_in=amount_tao,
                notes=f"Received from unstaking subnet {netuid}",
                is_spot_price_from_web=False,
                fiat_ticker=self.native_fiat,
            )
            transactions.append(in_tx)

        return transactions

    def _rao_to_tao(self, value: str) -> str:
        """Convert RAO (10^-9 TAO) to TAO."""
        try:
            rao = RP2Decimal(value)
            tao = rao / RP2Decimal(10**_TAO_DECIMALS)
            return str(tao)
        except (ValueError, TypeError):
            return "0"

    def _normalize_timestamp(self, timestamp: str) -> str:
        """Normalize timestamp to ISO format."""
        if not timestamp:
            return datetime.now(timezone.utc).isoformat()

        # Try parsing as various formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(timestamp, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue

        # If it's already ISO format, return as-is
        return timestamp

    def _get_alpha_asset_name(self, netuid: int) -> str:
        """Get the alpha token name for a subnet."""
        # Subnet alpha tokens follow the pattern SN{netuid}
        return f"SN{netuid}"