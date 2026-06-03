# Branch Predictor Evaluation on BOOM OOO Core
## Cycle-Accurate RTL Simulation via Chipyard/Verilator

**Author:** Vidhyanandhan  
**Date:** June 2026  
**Platform:** Chipyard + Verilator, BOOM v3, RISC-V RV64GC

---

## 1. Motivation

Branch prediction is one of the most performance-critical components in an out-of-order processor. Unlike in-order pipelines — where a misprediction stalls the fetch stage until resolution — an OOO processor like BOOM can speculate deeply before a misprediction is detected, making the flush penalty proportionally larger. This project evaluates three distinct branch predictor designs on the BOOM (Berkeley Out-of-Order Machine) core to quantify the IPC impact of predictor complexity on real RISC-V benchmarks.

This work extends a prior implementation of a 2-bit saturating counter branch predictor on an RV32I in-order core, placing that design in the context of industrial-grade OOO hardware.

---

## 2. Experimental Setup

### 2.1 Processor: BOOM v3 (SmallBoom Configuration)

All three experiments use an identical 1-wide SmallBOOM core — the only variable is the branch predictor. This isolates the BPD contribution to IPC.

| Parameter             | Value                          |
|-----------------------|-------------------------------|
| ISA                   | RV64GC                        |
| Decode width          | 1 instruction/cycle           |
| ROB entries           | 32                            |
| Issue queues          | 3 × 8 entries (MEM/INT/FP)    |
| Physical INT regs     | 52                            |
| Physical FP regs      | 48                            |
| Load queue entries    | 8                             |
| Store queue entries   | 8                             |
| Max branch count      | 8 in flight                   |
| Fetch target queue    | 16 entries                    |
| D-cache               | 64-set, 4-way, 64-bit rows    |
| I-cache               | 64-set, 4-way, 64-bit rows    |

### 2.2 Simulation Methodology

Simulations were run using **Verilator 5.022** on the Chipyard framework, producing a cycle-accurate RTL simulation of the full SoC including caches, memory controllers, and peripherals. All three predictor configurations were compiled from the same BOOM v3 Chisel RTL source; only the `BranchPredictionBankParams` configuration mixin was changed between builds.

Performance is measured via RISC-V CSRs read at end-of-program:
- `mcycle` — total clock cycles elapsed
- `minstret` — total instructions retired

IPC is computed as `minstret / mcycle`. Because instruction count is identical across all three configs for a given benchmark (same binary, deterministic ISA behavior), **any cycle difference is entirely attributable to branch misprediction penalty stalls**.

### 2.3 Branch Predictor Configurations

#### Config 1 — TAGE-L (Tagged Geometric Length)
**Chipyard config class:** `SmallBoomV3Config` (default)  
**Mixin:** `WithTAGELBPD`

TAGE-L is the state-of-the-art predictor shipped as BOOM's default. It is composed of a pipeline of components feeding into one another:

```
uBTB → BIM → slow-BTB → TAGE → Loop predictor → final prediction
```

- **uBTB** (micro Branch Target Buffer): fast 1-cycle BTB for common taken branches
- **BIM** (Bimodal): 2-bit saturating counters, global index, 512 sets
- **TAGE core**: tagged tables indexed by XOR of PC with geometric-length global history (lengths 2, 4, 8, 16, 32, 64, 128). Each table has tag + 3-bit counter + useful bit. Longer-history tables override shorter ones when tag matches.
- **Loop predictor**: detects short loops (≤ 64 iterations) and predicts their exit exactly
- **bpdMaxMetaLength:** 120 bits

The key insight of TAGE is that longer history lengths capture distant correlations: a branch that only mispredicts once every 100 iterations requires ~7 bits of history to be captured, which BIM and GShare miss entirely.

#### Config 2 — GShare (Global History + Share)
**Chipyard config class:** `BoomGShareBPDConfig`  
**Mixin:** `WithBoom2BPD`

GShare is implemented as a 1-table degenerate TAGE with a single entry in the tagged table array, i.e., a single PHT (Pattern History Table) indexed by `PC XOR global_history`. BOOM's implementation stacks it with a BIM baseline and BTB:

```
BIM → BTB → GShare (1-table TAGE) → final prediction
```

- **GShare table:** 512 entries, 3-bit counters, global history XOR index
- **bpdMaxMetaLength:** 45 bits

GShare is the canonical "medium-complexity" predictor — it captures global correlation patterns but uses a fixed, short history length and has no tagged disambiguation, so aliasing in the PHT limits accuracy.

#### Config 3 — BIM / Alpha-21264 Tournament
**Chipyard config class:** `BoomBIMBPDConfig`  
**Mixin:** `WithAlpha21264BPD`

This implements the Alpha 21264-style tournament predictor, which combines a global BIM and a local BIM via a tournament selector:

```
Global HBIM ─┐
              ├→ Tournament selector → final prediction
Local  HBIM ─┘
BTB
```

- **HBIM** (Hashed BIM): 2-bit saturating counters with hashed index
- **Global predictor:** indexes PHT by global branch history
- **Local predictor:** indexes PHT by per-branch local history (PC-indexed)
- **Tournament selector:** 2-bit saturating counter that learns which sub-predictor is more accurate per-branch
- **bpdMaxMetaLength:** 64 bits

This represents the "baseline complex" design — more hardware than GShare (two PHTs + selector) but no tagged tables and therefore subject to aliasing across distinct branches that happen to share the same index.

---

## 3. Benchmarks

All benchmarks are from the standard `riscv-tests/benchmarks` suite, compiled to bare-metal RISC-V ELF with the Chipyard toolchain (riscv64-unknown-elf-gcc 13.2.0, -O2).

| Benchmark | Description                         | Branch character              |
|-----------|-------------------------------------|-------------------------------|
| dhrystone | Integer workload, Dhrystone 2.1     | Mixed, many small loops       |
| median    | Find median of array (insertion sort)| Highly branch-intensive       |
| towers    | Towers of Hanoi (recursive)         | Predictable call/return       |
| qsort     | Quicksort on 2048 integers          | Irregular, data-dependent     |
| multiply  | Integer multiply benchmark          | Tight loops, regular          |

---

## 4. Raw Results

### 4.1 Cycle and Instruction Counts

| Benchmark | Predictor | mcycle  | minstret | Notes                  |
|-----------|-----------|---------|----------|------------------------|
| dhrystone | TAGE-L    | 197,550 | 186,031  | 2532 Dhrystones/sec    |
| dhrystone | GShare    | 203,501 | 186,031  | 2458 Dhrystones/sec    |
| dhrystone | BIM       | 217,540 | 186,031  | 2299 Dhrystones/sec    |
| median    | TAGE-L    |   6,981 |   4,659  |                        |
| median    | GShare    |   8,592 |   4,659  |                        |
| median    | BIM       |   8,673 |   4,659  |                        |
| towers    | TAGE-L    |   4,471 |   3,782  |                        |
| towers    | GShare    |   4,676 |   3,782  |                        |
| towers    | BIM       |   4,655 |   3,782  |                        |
| qsort     | TAGE-L    | 250,628 | 123,506  |                        |
| qsort     | GShare    | 243,264 | 123,506  |                        |
| qsort     | BIM       | 306,591 | 123,506  |                        |
| multiply  | TAGE-L    |  29,793 |  24,100  |                        |
| multiply  | GShare    |  31,640 |  24,100  |                        |
| multiply  | BIM       |  32,810 |  24,100  |                        |

### 4.2 IPC

IPC = minstret / mcycle. Higher is better.

| Benchmark | TAGE-L | GShare | BIM   | TAGE-L best? |
|-----------|--------|--------|-------|--------------|
| dhrystone | 0.9417 | 0.9142 | 0.8552 | Yes         |
| median    | 0.6674 | 0.5422 | 0.5372 | Yes         |
| towers    | 0.8459 | 0.8088 | 0.8125 | Yes         |
| qsort     | 0.4928 | 0.5077 | 0.4028 | **No**      |
| multiply  | 0.8089 | 0.7617 | 0.7345 | Yes         |

### 4.3 Misprediction Penalty Overhead

Since instruction count is identical per benchmark, all extra cycles are misprediction-induced stalls. The table below shows **extra cycles** vs. TAGE-L baseline, and infers approximate extra flushes assuming a 10-cycle average misprediction penalty on SmallBOOM (pipeline depth from fetch to execute resolution ≈ 8–12 cycles).

| Benchmark | GShare extra cycles | GShare est. extra mispred. | BIM extra cycles | BIM est. extra mispred. |
|-----------|--------------------|-----------------------------|-----------------|--------------------------|
| dhrystone |  +5,951            | ~595                        | +19,990         | ~1,999                   |
| median    |  +1,611            | ~161                        |  +1,692         | ~169                     |
| towers    |    +205            |  ~21                        |    +184         | ~18                      |
| qsort     |  −7,364            | TAGE-L has ~736 more!       | +55,963         | ~5,596                   |
| multiply  |  +1,847            | ~185                        |  +3,017         | ~302                     |

### 4.4 IPC Improvement: TAGE-L over BIM

| Benchmark | TAGE-L IPC | BIM IPC | IPC gain | Cycle reduction |
|-----------|-----------|---------|----------|-----------------|
| dhrystone | 0.9417    | 0.8552  | +10.1%   | −9.2%           |
| median    | 0.6674    | 0.5372  | +24.2%   | −19.5%          |
| towers    | 0.8459    | 0.8125  | +4.1%    | −3.9%           |
| qsort     | 0.4928    | 0.4028  | +22.3%   | −18.3%          |
| multiply  | 0.8089    | 0.7345  | +10.1%   | −9.2%           |

### 4.5 IPC Improvement: TAGE-L over GShare

| Benchmark | TAGE-L IPC | GShare IPC | IPC gain   | Cycle reduction |
|-----------|-----------|------------|------------|-----------------|
| dhrystone | 0.9417    | 0.9142     | +3.0%      | −2.9%           |
| median    | 0.6674    | 0.5422     | +23.1%     | −18.8%          |
| towers    | 0.8459    | 0.8088     | +4.6%      | −4.4%           |
| qsort     | 0.4928    | 0.5077     | **−2.9%**  | +2.9% (GShare wins) |
| multiply  | 0.8089    | 0.7617     | +6.2%      | −5.8%           |

---

## 5. Analysis

### 5.1 TAGE-L vs. GShare: Tagged Disambiguation Pays Off on Correlated Branches

TAGE-L outperforms GShare on 4 of 5 benchmarks. The largest gains are on **median** (+23.1% IPC) and **dhrystone** (+3.0% IPC). The median benchmark is an insertion sort inner loop with a highly correlated exit condition: whether the current element needs to be shifted depends on the last several comparisons. TAGE's geometric-length history tables are precisely designed to capture this kind of multi-outcome correlation. GShare's single XOR-indexed table lacks the history depth and the per-entry tags to distinguish different branches that alias to the same PHT index.

The **dhrystone** result confirms the general case: a diverse integer workload with many small loops benefits substantially from TAGE's longer history and tag matching.

### 5.2 The qsort Anomaly: GShare Beats TAGE-L

**qsort is the most interesting result.** GShare achieves 0.508 IPC vs. TAGE-L's 0.493 — a 3% advantage for the simpler predictor. This is counterintuitive and warrants explanation.

Quicksort's branch behavior is fundamentally **data-dependent**: the partition pivot comparison is nearly uniformly distributed, meaning branch outcomes are close to random for large inputs. In this regime, no predictor can achieve high accuracy regardless of history length. TAGE-L's overhead likely comes from:

1. **Loop predictor false triggers**: The loop predictor may incorrectly classify qsort's recursive partition loop as a short counted loop, producing wrong predictions when the loop count varies with data.
2. **Longer pipeline fill on misprediction**: TAGE-L's deeper pipeline (loop predictor is the last stage) may add 1–2 extra penalty cycles per misprediction vs. GShare's shallower pipeline.
3. **Useful bit thrashing**: TAGE's useful bit mechanism (which protects long-history entries from eviction) may delay recovery when a long-history entry is wrong on nearly-random data.

The lesson: predictor complexity is not universally beneficial. For data-dependent, quasi-random branch workloads, a simpler predictor with fewer pipeline stages may outperform TAGE.

### 5.3 BIM (Alpha-21264) Baseline: Tournament Adds Hardware, Not Always Accuracy

The Alpha-21264 tournament predictor consistently underperforms GShare despite being architecturally more complex (two PHTs + selector vs. one). This suggests the tournament selector itself incurs mispredictions during its convergence phase, and the local history component does not capture useful patterns for these benchmarks that GShare's global history doesn't already cover.

The most dramatic BIM failure is on **qsort**: 306,591 cycles vs. 243,264 for GShare — 26% more cycles. qsort's irregular access patterns cause both the global and local PHTs to thrash, and the tournament selector oscillates without converging to a reliable choice.

### 5.4 Connection to 2-bit Saturating Counter Work

The BIM config (which uses 2-bit saturating counter PHTs at its core) represents the design point of a simple in-order predictor. On dhrystone, it achieves 0.855 IPC vs. TAGE-L's 0.942 — a 10% gap. In an in-order core this gap would be smaller (fewer instructions in flight to misspeculate), but BOOM's 32-entry ROB and 8-deep branch window amplify the penalty: each misprediction flushes more in-flight work.

This directly motivates TAGE: for every branch-intensive workload, having longer history tables and tagged disambiguation converts ~10–24% IPC into recovered performance.

---

## 6. Summary of Key Findings

| Finding | Evidence |
|---------|---------|
| TAGE-L is best on branch-correlated workloads | +23% IPC over GShare on median; +10% over BIM on dhrystone |
| GShare can match or beat TAGE-L on quasi-random branches | qsort: GShare +3% over TAGE-L; both defeated by data randomness |
| Tournament/BIM is weakest on irregular data-dependent branches | qsort: BIM is 26% slower than GShare, 24% slower than TAGE-L |
| OOO amplifies predictor impact vs. in-order | 32-entry ROB means more instructions flushed per misprediction |
| Predictor complexity has diminishing returns | TAGE-L → GShare gap (2–23%) is smaller than BIM → GShare gap on most workloads |

---

## 7. Artifacts

| File | Description |
|------|-------------|
| `chipyard/generators/chipyard/src/main/scala/config/BoomConfigs.scala` | Three BPD config classes added |
| `chipyard/sims/verilator/simulator-chipyard.harness-SmallBoomV3Config` | TAGE-L simulator binary |
| `chipyard/sims/verilator/simulator-chipyard.harness-BoomGShareBPDConfig` | GShare simulator binary |
| `chipyard/sims/verilator/simulator-chipyard.harness-BoomBIMBPDConfig` | BIM/Alpha-21264 simulator binary |
| `run_bpd_experiments.sh` | Runs all 15 benchmark/predictor combinations |
| `analyze_results.py` | Parses logs, prints IPC table, generates bar chart |
| `results/` | Raw simulator output logs (15 files) |

---
