#!/usr/bin/env python3
"""
Mock Binance API Server for E2E Testing

This is a simple mock HTTP server that responds to Binance API endpoints
in a way compatible with CCXT. It's used to demonstrate environment variable
URL overrides for E2E testing.

Usage:
    # Run the server (defaults to port 8080)
    python mock_binance_server.py
    
    # Or specify a port
    python mock_binance_server.py --port 9000

Then in another terminal, set the environment variable and run your test:
    export DALI_BINANCE_API_URL=http://localhost:8080
    # ... run your test

The server responds to these CCXT-compatible endpoints:
- GET /api/v3/deposits - Returns mock deposit history
- GET /api/v3/withdrawals - Returns mock withdrawal history  
- GET /api/v3/account - Returns mock account info
- GET /api/v3/ticker/24hr - Returns mock ticker data
"""

import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import random


# Mock data for testing
MOCK_DEPOSITS = [
    {
        "id": "deposit_001",
        "amount": "0.5",
        "coin": "BTC",
        "network": "BTC",
        "status": "1",  # 1 = success
        "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
        "txId": "abc123def456",
        "insertTime": str(int((datetime.now() - timedelta(days=30)).timestamp() * 1000)),
        "transferType": "0",
        "confirmTimes": "3/3",
    },
    {
        "id": "deposit_002", 
        "amount": "10.0",
        "coin": "ETH",
        "network": "ETH",
        "status": "1",
        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0eB1E",
        "txId": "xyz789ghi012",
        "insertTime": str(int((datetime.now() - timedelta(days=15)).timestamp() * 1000)),
        "transferType": "0",
        "confirmTimes": "12/12",
    }
]

MOCK_WITHDRAWALS = [
    {
        "id": "withdraw_001",
        "amount": "0.1",
        "coin": "BTC",
        "network": "BTC",
        "status": "1",
        "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
        "txId": "withdraw123",
        "applyTime": str(int((datetime.now() - timedelta(days=5)).timestamp() * 1000)),
        "transferType": "0",
        "confirmTimes": "3/3",
        "fee": "0.0001",
    }
]

MOCK_ACCOUNT = {
    "makerCommission": 10,
    "takerCommission": 10,
    "buyerCommission": 0,
    "sellerCommission": 0,
    "canTrade": True,
    "canWithdraw": True,
    "canDeposit": True,
    "updateTime": int(datetime.now().timestamp() * 1000),
    "accountType": "SPOT",
    "balances": [
        {"asset": "BTC", "free": "1.5", "locked": "0.0"},
        {"asset": "ETH", "free": "20.0", "locked": "5.0"},
        {"asset": "USDT", "free": "10000.0", "locked": "0.0"},
    ]
}


class BinanceMockHandler(BaseHTTPRequestHandler):
    """HTTP request handler that mimics Binance API responses."""
    
    def log_message(self, format, *args):
        """Override to customize logging."""
        print(f"[Mock Binance] {args[0]}")
    
    def _send_json_response(self, data, status=200):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_GET(self):
        """Handle GET requests."""
        path = self.path.split("?")[0]  # Remove query parameters for routing
        
        # Route: /api/v3/deposits
        if path == "/api/v3/deposits":
            # Parse query parameters for filtering
            self._send_json_response(MOCK_DEPOSITS)
            
        # Route: /api/v3/withdrawals
        elif path == "/api/v3/withdrawals":
            self._send_json_response(MOCK_WITHDRAWALS)
            
        # Route: /api/v3/account
        elif path == "/api/v3/account":
            self._send_json_response(MOCK_ACCOUNT)
            
        # Route: /api/v3/ticker/24hr
        elif path == "/api/v3/ticker/24hr":
            self._send_json_response([
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "45000.00",
                    "priceChange": "1000.00",
                    "priceChangePercent": "2.27",
                    "volume": "50000.00",
                }
            ])
            
        # Route: /api/v3/exchangeInfo (for markets)
        elif path == "/api/v3/exchangeInfo":
            self._send_json_response({
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "type": "spot"
                    },
                    {
                        "symbol": "ETHUSDT", 
                        "status": "TRADING",
                        "baseAsset": "ETH",
                        "quoteAsset": "USDT",
                        "type": "spot"
                    }
                ]
            })
            
        # Route: /sapi/v1/asset/assetDividend (for dividends)
        elif path == "/sapi/v1/asset/assetDividend":
            self._send_json_response({
                "rows": [],
                "total": 0
            })
            
        # Default: 404 Not Found
        else:
            self._send_json_response({
                "code": -1,
                "msg": f"Unknown endpoint: {path}"
            }, 404)
    
    def do_POST(self):
        """Handle POST requests."""
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else ""
        
        path = self.path.split("?")[0]
        
        # Handle POST requests similar to GET
        self.do_GET()


def run_server(port: int = 8080):
    """Start the mock Binance server."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, BinanceMockHandler)
    print(f"Mock Binance API server running on http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock Binance API Server for E2E Testing")
    parser.add_argument(
        "--port", 
        type=int, 
        default=8080,
        help="Port to run the server on (default: 8080)"
    )
    args = parser.parse_args()
    run_server(args.port)