#!/usr/bin/env bash
# Run CoreMark on three BOOM branch predictor configs and collect results.
# Usage: bash run_bpd_experiments.sh
set -e

CHIPYARD="$HOME/Documents/BOOM_CPU/chipyard"
SIM_DIR="$CHIPYARD/sims/verilator"
RESULTS_DIR="$HOME/Documents/BOOM_CPU/results"
RISCV_TESTS="$CHIPYARD/.conda-env/riscv-tools/riscv64-unknown-elf/share/riscv-tests/benchmarks"

export PATH="$HOME/miniconda3/bin:$PATH"
source "$CHIPYARD/env.sh"

mkdir -p "$RESULTS_DIR"

CONFIGS=(
  "SmallBoomV3Config"
  "BoomGShareBPDConfig"
  "BoomBIMBPDConfig"
)

for CONFIG in "${CONFIGS[@]}"; do
  SIM="$SIM_DIR/simulator-chipyard.harness-${CONFIG}"

  if [ ! -f "$SIM" ]; then
    echo "ERROR: simulator not found: $SIM"
    echo "Build it first: cd $SIM_DIR && make CONFIG=$CONFIG -j16"
    continue
  fi

  echo "=== Running dhrystone on $CONFIG ==="
  "$SIM" "$RISCV_TESTS/dhrystone.riscv" \
    2>&1 | tee "$RESULTS_DIR/${CONFIG}-dhrystone.log"

  echo "=== Running median on $CONFIG ==="
  "$SIM" "$RISCV_TESTS/median.riscv" \
    2>&1 | tee "$RESULTS_DIR/${CONFIG}-median.log"

  echo "=== Running towers on $CONFIG ==="
  "$SIM" "$RISCV_TESTS/towers.riscv" \
    2>&1 | tee "$RESULTS_DIR/${CONFIG}-towers.log"

  echo "=== Running qsort on $CONFIG ==="
  "$SIM" "$RISCV_TESTS/qsort.riscv" \
    2>&1 | tee "$RESULTS_DIR/${CONFIG}-qsort.log"

  echo "=== Running multiply on $CONFIG ==="
  "$SIM" "$RISCV_TESTS/multiply.riscv" \
    2>&1 | tee "$RESULTS_DIR/${CONFIG}-multiply.log"

  echo "Done: $CONFIG"
done

echo ""
echo "Results written to $RESULTS_DIR"
echo "Run: python3 $HOME/Documents/BOOM_CPU/analyze_results.py"
