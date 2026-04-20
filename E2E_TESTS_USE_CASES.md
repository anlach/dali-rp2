# E2E Tests Use Cases

This document lists all end-to-end (E2E) test use cases covered in the rp2 and dali-rp2 repositories.

## Summary

- **dali-rp2**: 47 E2E tests
- **rp2**: 4 E2E tests
- **Total**: 51 E2E tests

---

## dali-rp2 E2E Tests

### Test File: test_yoroi_e2e.py (12 tests)

| Test Class | Test Method | Use Case |
|------------|-------------|----------|
| TestYoroiE2E | test_full_pipeline_yoroi_only | Full CSV→ODS pipeline with Yoroi CSV only |
| TestYoroiE2E | test_full_pipeline_with_minswap | Full pipeline with Yoroi + Minswap integration |
| TestYoroiE2E | test_unique_transaction_ids_generated | Verifies unique transaction ID generation |
| TestYoroiE2E | test_ods_output_generation | ODS file generation from Yoroi input |
| TestYoroiE2E | test_ods_output_contains_expected_assets | Verifies ADA and tokens in output |
| TestYoroiE2E | test_fiat_values_calculated | Fiat value calculation with mocked prices |
| TestYoroiE2E | test_minswap_swap_transactions | Minswap swap transaction handling |
| TestYoroiE2E | test_lp_transactions | LP removal transaction handling |
| TestYoroiE2E | test_transaction_timestamps_preserved | Timestamp preservation through pipeline |
| TestYoroiE2E | test_multiple_assets_from_swaps | Multiple token assets from swaps |
| TestYoroiE2EMocking | test_with_explicit_mock_converter | Explicit MockPairConverter usage |
| TestYoroiE2EMocking | test_error_handling_missing_csv | Error handling for missing CSV |

### Test File: test_csv_plugin_e2e.py (18 tests)

| Test Class | Test Method | Use Case |
|------------|-------------|----------|
| TestManualE2E | test_manual_in_transactions | Manual CSV "in" (Buy) transactions |
| TestManualE2E | test_manual_out_transactions | Manual CSV "out" (Sell) transactions |
| TestManualE2E | test_manual_intra_transactions | Manual CSV "intra" (transfer) transactions |
| TestManualE2E | test_manual_full_pipeline | All three manual CSV files together |
| TestManualE2E | test_manual_ods_output_generation | ODS file generation from manual CSV |
| TestManualE2E | test_manual_unique_transaction_ids | Unique ID generation for manual transactions |
| TestManualE2E | test_manual_assets_extracted | Asset extraction (e.g., BTC) |
| TestManualE2E | test_manual_fiat_values_calculated | Fiat value calculation for manual |
| TestBinanceE2E | test_binance_autoinvest_transactions | Binance autoinvest Buy transactions |
| TestBinanceE2E | test_binance_betheth_transactions | Binance bETH conversion transactions |
| TestBinanceE2E | test_binance_full_pipeline | Both Binance CSV files together |
| TestBinanceE2E | test_binance_ods_output_generation | ODS file generation from Binance |
| TestBinanceE2E | test_binance_assets_extracted | ETH and BTC asset extraction |
| TestBinanceE2E | test_binance_betheth_asset_conversion | ETH → bETH conversion |
| TestBinanceE2E | test_binance_autoinvest_notes | Meaningful notes in transactions |
| TestBinanceE2EMocking | test_binance_with_explicit_mock_converter | Explicit MagicMock for Binance |
| TestBinanceE2EMocking | test_error_handling_missing_csv | FileNotFoundError for CSV |
| TestBinanceE2EMocking | test_binance_error_handling_missing_csv | Additional error handling test |

### Test File: test_additional_coverage_e2e.py (17 tests)

| Test Class | Test Method | Use Case |
|------------|-------------|----------|
| TestDerivationInfo | test_parse_derivation_info_from_notes | Parse DERIVE info from notes |
| TestDerivationInfo | test_parse_derivation_info_no_match | No derivation info match |
| TestDerivationInfo | test_parse_derivation_info_empty_notes | Empty notes handling |
| TestMappedGraph | test_mapped_graph_creation | MappedGraph creation |
| TestMappedGraph | test_mapped_graph_with_vertexes | Graph with vertexes |
| TestCache | test_cache_save_and_load | Cache save and load |
| TestCache | test_cache_load_nonexistent | Load nonexistent cache |
| TestTransactionResolverEdgeCases | test_resolve_optional_fields_with_none | Optional field resolution |
| TestTransactionResolverEdgeCases | test_resolve_optional_fields_both_none | Both optional fields none |
| TestTransactionResolverEdgeCases | test_resolve_fields_with_numbers | Numeric field resolution |
| TestTransactionResolverEdgeCases | test_resolve_fields_numeric_conflict | Numeric conflict resolution |
| TestLPTokenHandling | test_lp_token_creation | LP token creation |
| TestAbstractPlugins | test_abstract_input_plugin_interface | AbstractInputPlugin interface |
| TestAbstractPlugins | test_abstract_pair_converter_interface | AbstractPairConverter interface |
| TestHistoricalBar | test_historical_bar_creation | HistoricalBar creation |
| TestConfiguration | test_keyword_enum | Keyword enum configuration |
| TestTransactionManifest | test_transaction_manifest_import | TransactionManifest import |

---

## rp2 E2E Tests

### Test File: test_dali_rp2_e2e.py (1 test)

| Test Class | Test Method | Use Case |
|------------|-------------|----------|
| TestDaliRp2E2E | test_dali_rp2_e2e | Full dali-rp2 → rp2 pipeline |

**Description**: Runs dali-rp2 to generate crypto_data.ods and crypto_data.ini, then runs rp2 on those outputs and verifies all expected report files are generated (fifo_open_positions.ods, fifo_rp2_full_report.ods, fifo_tax_report_us.ods).

### Test File: test_rp2_core_e2e.py (3 tests)

| Test Class | Test Method | Use Case |
|------------|-------------|----------|
| TestRP2CoreModules | test_rp2_decimal_operations | RP2 decimal operations |
| TestRP2CoreModules | test_rp2_error_types | RP2 error types |
| TestDaliRp2Output | test_dali_rp2_output_exists | Verify dali-rp2 output exists |

---

## Input Plugins Covered

### dali-rp2
- **manual**: Manual CSV plugin (in, out, intra transactions)
- **binance**: Binance.com supplemental CSV (autoinvest, betheth)
- **yoroi**: Yoroi wallet CSV export
- **minswap**: Minswap CSV (integrated with Yoroi)

### rp2
- Processes ODS/INI output from dali-rp2

---

## Test Data Files

- `dali-rp2/input/test_manual_in.csv`
- `dali-rp2/input/test_manual_out.csv`
- `dali-rp2/input/test_manual_intra.csv`
- `dali-rp2/input/test_binance_autoinvest.csv`
- `dali-rp2/input/test_binance_betheth.csv`
- `yoroi/*.csv` (Yoroi exports)

---

## GitHub Actions Workflows

- **dali-rp2**: `.github/workflows/unix_e2e_tests.yml`
- **rp2**: `.github/workflows/unix_e2e_tests.yml`

Both run E2E tests on push to main/master/develop and on pull requests.

---

## Notes

- All external API calls (price lookups) are mocked using MockPairConverter
- Tests use fixed prices for deterministic results (e.g., ADA=$0.35, BTC=$35000, ETH=$2000)
- HTML coverage reports generated in `htmlcov/` directories