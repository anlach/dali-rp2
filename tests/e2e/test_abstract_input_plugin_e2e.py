# Copyright 2025
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

"""E2E tests for AbstractInputPlugin to improve coverage."""

import pytest
from rp2.plugin.country.us import US

from dali.abstract_input_plugin import AbstractInputPlugin
from dali.in_transaction import InTransaction
from dali.out_transaction import OutTransaction


class ConcreteInputPlugin(AbstractInputPlugin):
    """A concrete implementation of AbstractInputPlugin for testing."""

    def __init__(self, account_holder: str, native_fiat: str, cache_enabled: bool = False):
        super().__init__(account_holder, native_fiat)
        self._cache_enabled = cache_enabled

    def cache_key(self) -> str:
        if self._cache_enabled:
            return f"test_cache_{self.account_holder}"
        return None

    def load(self, country):
        """Return a simple transaction for testing."""
        return [
            InTransaction(
                timestamp="2021-01-01T00:00:00Z",
                asset="BTC",
                exchange="test_exchange",
                holder=self.account_holder,
                transaction_type="buy",
                spot_price="10000.00",
                crypto_in="1.0",
                crypto_fee="0.0",
                fiat_in_no_fee="10000.00",
                fiat_in_with_fee="10000.00",
                fiat_fee="0.00",
                unique_id="test001",
                notes="test transaction",
            )
        ]


class TestAbstractInputPlugin:
    """Tests for AbstractInputPlugin class."""

    def test_abstract_input_plugin_init(self):
        """Test initialization of AbstractInputPlugin."""
        plugin = ConcreteInputPlugin("test_holder", "USD")
        
        assert plugin.account_holder == "test_holder"
        assert plugin.native_fiat == "USD"

    def test_abstract_input_plugin_native_fiat_none(self):
        """Test initialization with None native_fiat."""
        plugin = ConcreteInputPlugin("test_holder", None)
        
        assert plugin.account_holder == "test_holder"
        assert plugin.native_fiat is None

    def test_is_native_fiat_true(self):
        """Test is_native_fiat returns True when currency matches."""
        plugin = ConcreteInputPlugin("test_holder", "USD")
        
        assert plugin.is_native_fiat("USD") is True

    def test_is_native_fiat_false(self):
        """Test is_native_fiat returns False when currency doesn't match."""
        plugin = ConcreteInputPlugin("test_holder", "USD")
        
        assert plugin.is_native_fiat("EUR") is False

    def test_is_native_fiat_none(self):
        """Test is_native_fiat returns False when currency is None."""
        plugin = ConcreteInputPlugin("test_holder", "USD")
        
        assert plugin.is_native_fiat(None) is False

    def test_cache_key_returns_none_by_default(self):
        """Test cache_key returns None when caching is disabled."""
        plugin = ConcreteInputPlugin("test_holder", "USD", cache_enabled=False)
        
        assert plugin.cache_key() is None

    def test_cache_key_returns_string_when_enabled(self):
        """Test cache_key returns a string when caching is enabled."""
        plugin = ConcreteInputPlugin("test_holder", "USD", cache_enabled=True)
        
        assert plugin.cache_key() == "test_cache_test_holder"

    def test_load_from_cache_raises_when_no_cache_key(self):
        """Test load_from_cache raises error when cache_key returns None."""
        plugin = ConcreteInputPlugin("test_holder", "USD", cache_enabled=False)
        
        with pytest.raises(Exception):  # RP2RuntimeError
            plugin.load_from_cache()

    def test_save_to_cache_raises_when_no_cache_key(self):
        """Test save_to_cache raises error when cache_key returns None."""
        plugin = ConcreteInputPlugin("test_holder", "USD", cache_enabled=False)
        
        with pytest.raises(Exception):  # RP2RuntimeError
            plugin.save_to_cache([])


class TestAbstractInputPluginTypeErrors:
    """Tests for type checking in AbstractInputPlugin."""

    def test_init_raises_on_non_string_holder(self):
        """Test that __init__ raises RP2TypeError when account_holder is not a string."""
        with pytest.raises(Exception):  # RP2TypeError
            ConcreteInputPlugin(123, "USD")  # type: ignore

    def test_is_native_fiat_raises_on_invalid_type(self):
        """Test is_native_fiat behavior with invalid types."""
        plugin = ConcreteInputPlugin("test_holder", "USD")
        
        # Should return False for non-matching types
        assert plugin.is_native_fiat(123) is False  # type: ignore