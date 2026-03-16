# Coverage Progress Report - Coinbase/Coinbase Advanced E2E Tests

## Summary
Successfully added E2E tests to improve coverage for `coinbase.py` and `coinbase_advanced.py` plugins.

## Coverage Progress

| Module | Before | After | Change |
|--------|--------|-------|--------|
| coinbase.py | 63.94% | 68.96% | +5.02% |
| coinbase_advanced.py | 60.94% | 69.96% | +9.02% |

## Changes Made

### New Test File
- `tests/e2e/test_coinbase_coverage.py` - 30 new E2E tests

### Test Coverage Areas

1. **Swap/Trade Processing**
   - Buy/sell side matching
   - Trade transaction types (buy, sell, trade)

2. **Transfer Edge Cases**
   - Send to email (gifts)
   - Receive from email
   - Coinbase Earn reversals
   - Prime withdrawals
   - Pro deposits
   - Unknown source receives

3. **Gain/Income Processing**
   - Interest income
   - Staking rewards
   - Inflation rewards

4. **Fiat Transactions**
   - Fiat deposits with titles
   - Fiat withdrawals
   - Card buyback (refunds)

5. **Stablecoin Processing**
   - USDC send/receive
   - Network transaction handling

6. **Advanced Trade Fills**
   - Commission handling for buys
   - Commission handling for sells
   - USDC spot price handling

7. **Helper Methods**
   - Credit card spend detection

## Commit
```
95a6114 Add comprehensive E2E tests for Coinbase and Coinbase Advanced plugins
```

## Remaining Work
To reach 80%+, the following areas still need coverage:
- Full `load()` method integration tests with mocked HTTP responses
- API pagination handling
- Error response validation
- Swap post-processing edge cases
- More transaction type combinations