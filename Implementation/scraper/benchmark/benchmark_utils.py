"""
benchmark_utils.py - Performance measurement utilities
"""
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager

class PerformanceTimer:
    """Track timing for different stages of the pipeline"""
    
    def __init__(self, name: str = "benchmark"):
        self.name = name
        self.start_time = None
        self.stages: Dict[str, float] = {}
        self.stage_start: Dict[str, float] = {}
        self.metadata: Dict[str, Any] = {}
    
    def start(self):
        """Start overall timer"""
        self.start_time = time.time()
        self.metadata["start_time"] = datetime.now().isoformat()
    
    def end(self):
        """End overall timer"""
        if self.start_time:
            total = time.time() - self.start_time
            self.metadata["total_time"] = total
            self.metadata["end_time"] = datetime.now().isoformat()
            return total
        return 0
    
    @contextmanager
    def stage(self, stage_name: str):
        """Context manager for timing a stage"""
        start = time.time()
        self.stage_start[stage_name] = start
        try:
            yield
        finally:
            elapsed = time.time() - start
            self.stages[stage_name] = elapsed
            print(f"[TIMING] {stage_name}: {elapsed:.2f}s")
    
    def add_metadata(self, key: str, value: Any):
        """Add metadata about the run"""
        self.metadata[key] = value
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all timings"""
        return {
            "name": self.name,
            "metadata": self.metadata,
            "stages": self.stages,
            "total_time": self.metadata.get("total_time", 0),
        }
    
    def save(self, output_path: str):
        """Save timing results to JSON file"""
        summary = self.get_summary()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n[TIMING] Results saved to {output_path}")
    
    def print_summary(self):
        """Print a formatted summary"""
        print("\n" + "="*60)
        print(f"PERFORMANCE SUMMARY: {self.name}")
        print("="*60)
        
        if self.metadata:
            print("\nMetadata:")
            for key, value in self.metadata.items():
                if key not in ["total_time", "start_time", "end_time"]:
                    print(f"  {key}: {value}")
        
        print("\nStage Timings:")
        total_stage_time = sum(self.stages.values())
        for stage, elapsed in sorted(self.stages.items(), key=lambda x: x[1], reverse=True):
            percentage = (elapsed / total_stage_time * 100) if total_stage_time > 0 else 0
            print(f"  {stage:30s}: {elapsed:6.2f}s ({percentage:5.1f}%)")
        
        total = self.metadata.get("total_time", total_stage_time)
        print(f"\n{'Total Time':30s}: {total:6.2f}s")
        print("="*60 + "\n")


def compare_benchmarks(before_path: str, after_path: str):
    """Compare two benchmark results"""
    with open(before_path, "r") as f:
        before = json.load(f)
    with open(after_path, "r") as f:
        after = json.load(f)
    
    print("\n" + "="*70)
    print("BENCHMARK COMPARISON")
    print("="*70)
    
    before_total = before.get("total_time", 0)
    after_total = after.get("total_time", 0)
    
    if before_total > 0:
        speedup = before_total / after_total if after_total > 0 else 0
        improvement = ((before_total - after_total) / before_total) * 100 if before_total > 0 else 0
        print(f"\nOverall Performance:")
        print(f"  Before: {before_total:.2f}s")
        print(f"  After:  {after_total:.2f}s")
        if speedup > 0:
            print(f"  Speedup: {speedup:.2f}x faster")
            print(f"  Improvement: {improvement:.1f}% faster")
        else:
            print(f"  Speedup: N/A (after time is 0)")
    
    print(f"\nStage-by-Stage Comparison:")
    print(f"{'Stage':<30} {'Before':>10} {'After':>10} {'Speedup':>10} {'Improvement':>12}")
    print("-" * 72)
    
    all_stages = set(before.get("stages", {}).keys()) | set(after.get("stages", {}).keys())
    for stage in sorted(all_stages):
        before_time = before.get("stages", {}).get(stage, 0)
        after_time = after.get("stages", {}).get(stage, 0)
        
        if before_time > 0 and after_time > 0:
            speedup = before_time / after_time
            improvement = ((before_time - after_time) / before_time) * 100
            print(f"{stage:<30} {before_time:>10.2f}s {after_time:>10.2f}s {speedup:>10.2f}x {improvement:>11.1f}%")
        elif before_time > 0:
            print(f"{stage:<30} {before_time:>10.2f}s {'N/A':>10} {'N/A':>10} {'N/A':>12}")
        elif after_time > 0:
            print(f"{stage:<30} {'N/A':>10} {after_time:>10.2f}s {'N/A':>10} {'N/A':>12}")
    
    print("="*70 + "\n")

