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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


class InputPlugin(AbstractInputPlugin):
    __PLUGIN_NAME: str = "taostats_REST"

    def __init__(
        self,
        account_holder: str,
        api_key: str,
        native_fiat: Optional[str] = None,
    ) -> None:
        super().__init__(account_holder=account_holder, native_fiat=native_fiat)
        self.__api_key: str = api_key
        self.__logger: logging.Logger = create_logger(f"{self.__PLUGIN_NAME}/{self.account_holder}")

    def cache_key(self) -> Optional[str]:
        return f"taostats-{self.account_holder}"

    def load(self, country: AbstractCountry) -> List[AbstractTransaction]:
        result: List[AbstractTransaction] = []
        delegations: List[Dict[str, Any]] = self._fetch_delegations()

        for delegation in delegations:
            transactions = self._process_delegation(delegation)
            result.extend(transactions)

        self.__logger.info(f"Loaded {len(result)} transactions from Taostats for {self.account_holder}")
        return result

    def _fetch_delegations(self) -> List[Dict[str, Any]]:
        """Fetch delegation history from Taostats API."""
        url = f"{_API_BASE_URL}/delegation/history"
        headers = {
            "Authorization": self.__api_key,
            "Content-Type": "application/json",
        }
        params = {
            "coldkey": self.account_holder,
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
        if amount_tao and RP2Decimal(amount_tao) > 0:
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
                transaction_type=Keyword.STAKING.value,
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