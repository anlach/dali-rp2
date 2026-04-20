#!/usr/bin/env python3
"""
Demonstration script showing environment variable URL override for E2E testing.

This script demonstrates how to use the DALI_<EXCHANGE>_API_URL environment 
variables to redirect API calls to a mock server.

Usage:
    # 1. First, start the mock server in one terminal:
    #    python mock_binance_server.py --port 8080
    
    # 2. Then run this demo with the environment variable set:
    #    DALI_BINANCE_API_URL=http://localhost:8080 python demo_url_override.py
    
    # 3. Without the environment variable, it will use the real Binance API:
    #    python demo_url_override.py
"""

import os
import sys
import json

# Add the dali-rp2 src to the path
sys.path.insert(0, "/home/linuxuser/.openclaw/workspace/rp2-work/dali-rp2/src")

from dali.abstract_input_plugin import AbstractInputPlugin
from dali.abstract_ccxt_input_plugin import AbstractCcxtInputPlugin


def demonstrate_env_var_override():
    """Demonstrate how environment variable URL override works."""
    
    print("=" * 60)
    print("Environment Variable URL Override Demonstration")
    print("=" * 60)
    
    # Create a mock class that extends AbstractInputPlugin for testing
    class MockPlugin(AbstractInputPlugin):
        def __init__(self):
            super().__init__("test_holder", "USD")
        
        def load(self, country):
            return []
    
    # Test with the mock plugin
    plugin = MockPlugin()
    
    # Test various exchanges
    exchanges = ["Binance", "Coinbase", "Kraken", "Bitbank", "Coincheck"]
    
    print("\n1. Testing _get_api_url_override() with no environment variables set:")
    print("-" * 50)
    for exchange in exchanges:
        url = plugin._get_api_url_override(exchange)
        print(f"   {exchange:12} -> {url if url else '(None, uses default)'}")
    
    # Test with environment variables set
    print("\n2. Testing _get_api_url_override() with environment variables set:")
    print("-" * 50)
    
    # Set some test environment variables
    os.environ["DALI_BINANCE_API_URL"] = "http://localhost:8080"
    os.environ["DALI_COINBASE_API_URL"] = "http://localhost:9000"
    # Leave Kraken unset to test default behavior
    
    for exchange in exchanges:
        url = plugin._get_api_url_override(exchange)
        if url:
            print(f"   {exchange:12} -> {url}")
        else:
            print(f"   {exchange:12} -> (None, uses default)")
    
    # Cleanup
    del os.environ["DALI_BINANCE_API_URL"]
    del os.environ["DALI_COINBASE_API_URL"]
    
    print("\n3. Environment variable naming convention:")
    print("-" * 50)
    print("   DALI_BINANCE_API_URL  -> Overrides Binance API endpoint")
    print("   DALI_COINBASE_API_URL -> Overrides Coinbase API endpoint")  
    print("   DALI_KRAKEN_API_URL   -> Overrides Kraken API endpoint")
    print("   DALI_BITBANK_API_URL  -> Overrides Bitbank API endpoint")
    
    print("\n4. How it works:")
    print("-" * 50)
    print("   - CCXT-based plugins (Binance, Kraken): Use 'urls' option")
    print("   - REST plugins (Coinbase): Use the URL in HTTP requests")
    print("   - The override is applied during client initialization")
    print("   - No environment variable = use default exchange URL")
    
    print("\n5. E2E Testing Workflow:")
    print("-" * 50)
    print("   1. Start mock server: python mock_binance_server.py --port 8080")
    print("   2. Set environment variable: export DALI_BINANCE_API_URL=http://localhost:8080")
    print("   3. Run your tests - they will hit the mock server instead of real API")
    print("   4. This provides true E2E testing at the HTTP level")
    
    print("\n" + "=" * 60)
    print("Demonstration complete!")
    print("=" * 60)


if __name__ == "__main__":
    demonstrate_env_var_override()