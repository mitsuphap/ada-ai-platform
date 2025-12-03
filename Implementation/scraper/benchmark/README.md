# Benchmarking Guide

This guide explains how to measure and compare performance before and after optimizations.

**Note:** All benchmark scripts are located in the `benchmark/` directory. Run them from the `scraper/` directory.

## Quick Start

### 1. Run Baseline Benchmark (Before Optimization)

```bash
# From the scraper directory
cd Implementation/scraper
python benchmark/run_benchmark.py "your search query" baseline

# This will save results to: benchmarks/baseline_<timestamp>.json
```

### 2. Apply Optimizations

Make your code changes (e.g., add parallel processing, increase workers, etc.)

### 3. Run Optimized Benchmark

```bash
# Run with same query
python benchmark/run_benchmark.py "your search query" optimized

# This will save results to: benchmarks/optimized_<timestamp>.json
```

### 4. Compare Results

```bash
# Compare the two runs
python benchmark/compare_benchmarks.py benchmarks/baseline_*.json benchmarks/optimized_*.json
```

## Detailed Usage

### Full Pipeline Benchmarking

The `benchmark/run_benchmark.py` script runs the entire pipeline with detailed timing:

```bash
# From the scraper directory
python benchmark/run_benchmark.py "find email addresses of VPs at universities" my_test
```

This will:
1. Generate queries (timed)
2. Run Google searches (timed)
3. Classify results (timed)
4. Scrape and extract data (timed)

Results are saved to `benchmarks/my_test_<timestamp>.json`

### Individual Stage Testing

Test specific stages with different configurations:

#### Test Scraping Performance

```bash
# Test scraping with different worker counts (1, 3, 5, 10)
python benchmark/test_stage_timing.py scraping
```

#### Test Classification Performance

```bash
# Test classification with different batch sizes (5, 10, 20)
python benchmark/test_stage_timing.py classification
```

#### Test Google Search Performance

```bash
# Test Google search timing
python benchmark/test_stage_timing.py google
```

### Comparing Benchmarks

Compare any two benchmark files:

```bash
# Exact file paths
python benchmark/compare_benchmarks.py benchmarks/baseline_1234567890.json benchmarks/optimized_1234567891.json

# Or use wildcards (uses most recent)
python benchmark/compare_benchmarks.py benchmarks/baseline_*.json benchmarks/optimized_*.json
```

## Understanding the Output

### Performance Summary

When you run a benchmark, you'll see:

```
[TIMING] query_generation: 2.34s
[TIMING] google_search: 15.67s
[TIMING] classification: 8.23s
[TIMING] scraping: 45.12s

PERFORMANCE SUMMARY: pipeline_run
============================================================
Metadata:
  num_seeds: 25
  max_workers: 10
  queries_generated: 5

Stage Timings:
  scraping                    :  45.12s ( 63.5%)
  google_search               :  15.67s ( 22.1%)
  classification              :   8.23s ( 11.6%)
  query_generation            :   2.34s (  3.3%)

Total Time                   :  71.36s
============================================================
```

### Comparison Output

When comparing benchmarks:

```
BENCHMARK COMPARISON
======================================================================

Overall Performance:
  Before: 71.36s
  After:  18.45s
  Speedup: 3.87x faster
  Improvement: 74.1% faster

Stage-by-Stage Comparison:
Stage                          Before     After    Speedup   Improvement
----------------------------------------------------------------------
scraping                       45.12s    12.34s      3.66x        72.7%
google_search                  15.67s     4.12s      3.80x        73.7%
classification                  8.23s     1.89s      4.35x        77.0%
query_generation                2.34s     2.10s      1.11x        10.3%
======================================================================
```

## Best Practices

1. **Use the same test query** for before/after comparisons
2. **Run multiple times** and average results (network/API variability)
3. **Test individual stages** to identify bottlenecks
4. **Save benchmark files** with descriptive names (e.g., `baseline_v1`, `optimized_parallel_v1`)
5. **Compare stage-by-stage** to see which optimizations helped most

## Benchmark File Format

Benchmark files are JSON with this structure:

```json
{
  "name": "pipeline_run",
  "metadata": {
    "start_time": "2025-01-15T10:30:00",
    "end_time": "2025-01-15T10:31:11",
    "total_time": 71.36,
    "num_seeds": 25,
    "max_workers": 10
  },
  "stages": {
    "query_generation": 2.34,
    "google_search": 15.67,
    "classification": 8.23,
    "scraping": 45.12
  },
  "total_time": 71.36
}
```

## Troubleshooting

### "No files found matching"
- Make sure you've run at least one benchmark first
- Check that the `benchmarks/` directory exists in the scraper directory

### "Module not found: benchmark_utils"
- Make sure you're running from the `Implementation/scraper/` directory
- The benchmark scripts automatically add the parent directory to the Python path
- If issues persist, check that `benchmark/__init__.py` exists

### Timing seems inconsistent
- Network latency and API response times vary
- Run multiple times and average the results
- Use the same test data for fair comparison

## Directory Structure

```
Implementation/scraper/
├── benchmark/              # Benchmark utilities
│   ├── __init__.py        # Package initialization
│   ├── benchmark_utils.py  # Core timing utilities
│   ├── run_benchmark.py    # Full pipeline benchmark
│   ├── compare_benchmarks.py  # Comparison tool
│   ├── test_stage_timing.py   # Individual stage testing
│   └── README.md          # This file
├── benchmarks/            # Benchmark results (JSON files)
├── llm_scrape_from_seeds.py  # Uses benchmark utilities
├── classify_search_results.py  # Uses benchmark utilities
└── ...
```
