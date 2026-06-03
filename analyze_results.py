#!/usr/bin/env python3
"""Parse BOOM Verilator simulation logs and plot branch predictor comparison."""

import re
import os
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"

CONFIGS = {
    "SmallBoomV3Config": "TAGE-L",
    "BoomGShareBPDConfig": "GShare",
    "BoomBIMBPDConfig":   "BIM (Alpha-21264)",
}

BENCHMARKS = ["dhrystone", "median", "towers", "qsort", "multiply"]


def parse_log(path: Path) -> dict:
    """Extract cycle count, instruction count, and IPC from a simulation log."""
    text = path.read_text()
    result = {}

    # BOOM prints: "mcycle = <N>" and "minstret = <N>"
    m = re.search(r"mcycle\s*=\s*(\d+)", text)
    if m:
        result["cycles"] = int(m.group(1))

    m = re.search(r"minstret\s*=\s*(\d+)", text)
    if m:
        result["instret"] = int(m.group(1))

    # Some benchmarks print explicit IPC line
    m = re.search(r"IPC\s*=\s*([\d.]+)", text)
    if m:
        result["ipc"] = float(m.group(1))
    elif "cycles" in result and "instret" in result and result["cycles"] > 0:
        result["ipc"] = result["instret"] / result["cycles"]

    return result


def collect():
    data = {}
    for config_key, config_label in CONFIGS.items():
        data[config_label] = {}
        for bench in BENCHMARKS:
            log = RESULTS_DIR / f"{config_key}-{bench}.log"
            if not log.exists():
                print(f"  MISSING: {log.name}")
                continue
            parsed = parse_log(log)
            if parsed:
                data[config_label][bench] = parsed
            else:
                print(f"  WARN: could not parse {log.name}")
    return data


def print_table(data):
    print("\n=== IPC by Benchmark and Predictor ===\n")
    header = f"{'Benchmark':<12}" + "".join(f"{lbl:>20}" for lbl in CONFIGS.values())
    print(header)
    print("-" * len(header))
    for bench in BENCHMARKS:
        row = f"{bench:<12}"
        for lbl in CONFIGS.values():
            ipc = data.get(lbl, {}).get(bench, {}).get("ipc")
            row += f"{'N/A':>20}" if ipc is None else f"{ipc:>20.4f}"
        print(row)
    print()


def plot(data):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not installed — skipping plot. Run: pip install matplotlib")
        return

    labels = list(CONFIGS.values())
    x = np.arange(len(BENCHMARKS))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    for i, lbl in enumerate(labels):
        ipcs = [data.get(lbl, {}).get(b, {}).get("ipc", 0) for b in BENCHMARKS]
        ax.bar(x + i * width, ipcs, width, label=lbl)

    ax.set_xlabel("Benchmark")
    ax.set_ylabel("IPC")
    ax.set_title("BOOM Branch Predictor Comparison — IPC by Benchmark")
    ax.set_xticks(x + width)
    ax.set_xticklabels(BENCHMARKS)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    out = Path(__file__).parent / "results" / "bpd_ipc_comparison.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print(f"Plot saved to {out}")
    plt.show()


if __name__ == "__main__":
    if not RESULTS_DIR.exists():
        print(f"Results directory not found: {RESULTS_DIR}")
        print("Run bash run_bpd_experiments.sh first.")
        sys.exit(1)

    data = collect()
    print_table(data)
    plot(data)
