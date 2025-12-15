"""
compare_benchmarks.py - Compare before/after benchmark results
"""
import sys
import glob
from pathlib import Path

# Import from same directory
from benchmark_utils import compare_benchmarks

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python compare_benchmarks.py <before.json> <after.json>")
        print("\nOr use wildcards:")
        print("  python compare_benchmarks.py benchmarks/baseline_*.json benchmarks/optimized_*.json")
        sys.exit(1)
    
    before_path = sys.argv[1]
    after_path = sys.argv[2]
    
    # Handle wildcards
    if "*" in before_path:
        before_files = glob.glob(before_path)
        if not before_files:
            print(f"No files found matching: {before_path}")
            sys.exit(1)
        before_path = sorted(before_files)[-1]  # Use most recent
        print(f"Using: {before_path}")
    
    if "*" in after_path:
        after_files = glob.glob(after_path)
        if not after_files:
            print(f"No files found matching: {after_path}")
            sys.exit(1)
        after_path = sorted(after_files)[-1]  # Use most recent
        print(f"Using: {after_path}")
    
    compare_benchmarks(before_path, after_path)

