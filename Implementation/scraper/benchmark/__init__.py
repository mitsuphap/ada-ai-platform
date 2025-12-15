"""
Benchmark utilities for performance testing and monitoring.

This module provides tools for measuring and comparing performance
of the scraper pipeline.
"""

from .benchmark_utils import PerformanceTimer, compare_benchmarks

__all__ = ['PerformanceTimer', 'compare_benchmarks']

