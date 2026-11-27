# Testing Guide

This guide explains how to set up the environment, run the benchmark from scratch, inspect individual test cases, and verify the generated results. All commands below should be run from the repository root directory (`terraform-security-tools-comparison/`).

---

## 1. Prerequisites

The benchmark pipeline is implemented in a single Python script ([`scripts/benchmark.py`](../scripts/benchmark.py)) that uses only the Python standard library, so no external Python packages or virtual environments are needed. Both scanners run inside Docker containers using pinned images, meaning neither Checkov nor KICS needs to be installed on the host machine.

Required software:
- **Git**
- **Python 3.8+** (`python` or `python3` depending on the operating system)
- **Docker** (Docker Desktop on Windows/macOS, or Docker Engine on Linux, with the daemon running)

Optional software:
- **Terraform CLI** (`v1.17.2` or compatible), needed only if you want to run `terraform fmt` to check HCL formatting. The benchmark script checks that all 24 expected `.tf` files are present, have balanced braces, and contain AWS resource blocks.
- **LaTeX distribution with `pdflatex`** (such as MiKTeX on Windows or TeX Live on Linux/macOS), needed only if you want to recompile [`docs/report/main.pdf`](report/main.pdf) from [`docs/report/main.tex`](report/main.tex).

---

## 2. Environment Setup

### 2.1 Clone the repository

```bash
git clone https://github.com/LBartalucci/terraform-security-tools-comparison.git
cd terraform-security-tools-comparison
```

### 2.2 Check Python and Docker

```bash
python --version
docker --version
docker info
```

On Linux or macOS, use `python3` if `python` is not mapped to Python 3. If `docker info` reports a connection error, start Docker Desktop or the system Docker service before continuing.

### 2.3 Pull the scanner Docker images

The container versions used for the benchmark are defined in [`scripts/docker-versions.env`](../scripts/docker-versions.env) (`bridgecrew/checkov:3.4.5` and `checkmarx/kics:v2.2.1`). While Docker will automatically pull missing images during the first scan, downloading them ahead of time ensures the benchmark runs immediately without network delays:

```bash
docker pull bridgecrew/checkov:3.4.5
docker pull checkmarx/kics:v2.2.1
docker images
```

---

## 3. Running the Benchmark Pipeline

Running [`scripts/benchmark.py`](../scripts/benchmark.py) executes the four stages of the evaluation pipeline:
1. **`[1/4] Checking Terraform files...`** - Verifies that all 24 `.tf` files listed in [`benchmark/expected-results.json`](../benchmark/expected-results.json) exist in [`benchmark/cases/`](../benchmark/cases/), have balanced braces, and contain AWS resource declarations.
2. **`[2/4] Running Checkov and KICS scans via Docker...`** - Scans each of the 24 Terraform files one by one in isolated Docker containers (48 runs in total) so repeated resource names across vulnerable and fixed files do not collide. It also records total scan times and replaces local host paths in the raw JSON outputs with repository-relative paths (or prints `[2/4] Skipping Docker scans (--skip-scan)...` when `--skip-scan` is passed).
3. **`[3/4] Normalizing results...`** - Reads the raw JSON reports from both tools, verifies that every expected case has both a Checkov and KICS report, deduplicates repeated triggers of the same rule within a file, matches findings against the expected rule IDs in [`benchmark/expected-results.json`](../benchmark/expected-results.json), and separates targeted findings from unrelated best-practice alerts.
4. **`[4/4] Building metrics...`** - Computes classification metrics (`TP`, `FN`, `TN`, `FP`, Precision, Recall, F1-score, FPR, FNR), per-category detection coverage, signal-to-noise ratios (SNR), KICS severity distributions, and execution times.

### 3.1 Full benchmark run

```bash
python scripts/benchmark.py
```

Clears any previous raw outputs in `results/raw/checkov/` and `results/raw/kics/`, executes all 48 Docker scans across the 24 Terraform cases, writes the new raw JSON reports and timing data to `results/raw/`, and generates the normalized comparison and metric files in `results/normalized/`. Because 48 containers are launched sequentially, a full run takes roughly 7 to 8 minutes on a typical laptop (around 466 seconds in our reference run).

### 3.2 Recomputing results from existing raw outputs

```bash
python scripts/benchmark.py --skip-scan
```

Skips the Docker scanning step (Stage 2) and runs validation, normalization, and metric calculation using the raw JSON files already stored in `results/raw/`. This finishes in less than a second and regenerates all five files in `results/normalized/` while keeping the existing scan timings in `results/raw/run-metadata.json`.

### 3.3 Command-line options

```bash
python scripts/benchmark.py --help
```

Supported CLI flags: `--skip-scan`, `--cases-dir`, `--expected-path`, `--raw-dir`, `--norm-dir`, `--versions-path`, and `--docker-cmd`.

---

## 4. Scanning a Single Terraform File Directly

In addition to running the full 24-file script, you can run either scanner directly on a single `.tf` file via Docker to inspect its raw console output in a few seconds without modifying the files in `results/`.

### 4.1 Single-file scan with Checkov

**PowerShell (Windows):**
```powershell
docker run --rm -v "${PWD}/benchmark/cases:/workspace/cases:ro" bridgecrew/checkov:3.4.5 -f /workspace/cases/EN-01-vulnerable.tf --framework terraform
```

**Bash (Linux / macOS / Git Bash):**
```bash
docker run --rm -v "$(pwd)/benchmark/cases:/workspace/cases:ro" bridgecrew/checkov:3.4.5 -f /workspace/cases/EN-01-vulnerable.tf --framework terraform
```

Running the same command on `EN-01-fixed.tf` shows why Checkov records a false positive on the fixed S3 encryption case: rule `CKV_AWS_145` requires KMS encryption (`aws:kms`) on every bucket and flags buckets configured with standard `AES256` server-side encryption.

### 4.2 Single-file scan with KICS

**PowerShell (Windows):**
```powershell
docker run --rm -v "${PWD}/benchmark/cases:/workspace/cases:ro" checkmarx/kics:v2.2.1 scan -p /workspace/cases/EN-01-vulnerable.tf
```

**Bash (Linux / macOS / Git Bash):**
```bash
docker run --rm -v "$(pwd)/benchmark/cases:/workspace/cases:ro" checkmarx/kics:v2.2.1 scan -p /workspace/cases/EN-01-vulnerable.tf
```

Comparing `EN-01-vulnerable.tf` and `NW-03-vulnerable.tf` illustrates two characteristic KICS behaviors observed in the benchmark: on `EN-01-vulnerable.tf`, KICS does not flag the bucket when the separate S3 encryption resource is omitted; on `NW-03-vulnerable.tf` (`protocol = "-1"`, all ports open to `0.0.0.0/0`), KICS outputs 137 findings for a single resource because query `381c3f2a` tests the open port range against 126 entries in its sensitive-port list one by one.

---

## 5. Generated Output Files

The pipeline writes its outputs into two subdirectories under `results/`.

### 5.1 Raw outputs (`results/raw/`)

These files store the JSON output produced by both scanners, with local filesystem paths sanitized to repository-relative paths (`benchmark/cases/<file>.tf`):

| File / Directory | Format | Description |
|---|---|---|
| `results/raw/checkov/<CASE>.json` | JSON (24 files) | Sanitized Checkov JSON report for each `.tf` file. Failed checks appear under `results.failed_checks`, listing `check_id` (e.g., `CKV_AWS_145`), `check_name`, `resource`, and `file_line_range`. Checkov's open-source CLI leaves `"severity": null` when run without a Prisma Cloud API key. |
| `results/raw/kics/<CASE>/kics.json` | JSON (24 folders) | Sanitized KICS JSON report for each `.tf` file. Triggered rules appear under `queries[]`, including `query_id`, `query_name`, `severity` (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`), and the affected `files[]` entries. |
| `results/raw/run-metadata.json` | JSON | Stores the UTC execution timestamp (`generated_at`), the relative cases path (`benchmark/cases`), the number of scanned Terraform files (`24`), and the total execution time in seconds for Checkov (`checkov_seconds_total`) and KICS (`kics_seconds_total`). |

### 5.2 Normalized outputs (`results/normalized/`)

These files are produced by comparing the raw findings against the ground-truth baseline in [`benchmark/expected-results.json`](../benchmark/expected-results.json):

| File | Format | Description |
|---|---|---|
| [`results/normalized/comparison.md`](../results/normalized/comparison.md) | Markdown | Case-by-case comparison across all 24 Terraform files. Reports the classification outcome (`detected`, `missed-or-no-applicable-rule`, `clean`, or `unexpected-targeted-finding`), the ratio of targeted findings to total findings (`Targeted / Total`), and a root-cause breakdown of the three cases where the two scanners disagree (`EN-01` vulnerable, `ID-02` vulnerable, and `EN-01` corrected). |
| [`results/normalized/metrics.md`](../results/normalized/metrics.md) | Markdown | Aggregate evaluation tables covering overall classification performance (`TP`, `FN`, `TN`, `FP`, Precision, Recall, F1-score, FPR, FNR), per-category detection coverage, operational signal-to-noise ratios and scan timings, and the KICS severity distribution. |
| [`results/normalized/comparison.csv`](../results/normalized/comparison.csv) | CSV | 13-column tabular export of the 24 case-level records (`Id`, `Type`, `Category`, `File`, `ExpectedIssue`, `CheckovStatus`, `KicsStatus`, `CheckovTargetedRuleCount`, `KicsTargetedRuleCount`, `CheckovUniqueRuleCount`, `KicsUniqueRuleCount`, `CheckovAllFindingCount`, `KicsAllFindingCount`). |
| [`results/normalized/comparison.json`](../results/normalized/comparison.json) | JSON | Detailed machine-readable data for all 24 cases, containing the classification status, targeted rule and instance counts, deduplicated `CheckovTargetedFindings`, `KicsTargetedFindings`, `CheckovAllFindings`, `KicsAllFindings` (each recording `Occurrences` and affected `Resource`), `DisagreementReason`, and `RiskProfile`. |
| [`results/normalized/metrics.json`](../results/normalized/metrics.json) | JSON | Machine-readable version of all metrics reported in `metrics.md`, stored under the top-level keys `Metrics`, `CategoryBreakdown`, `KicsSeverityCounts`, and `ExecutionMetadata`. |

---

## 6. Verifying the Results

Once the script completes, open [`results/normalized/metrics.md`](../results/normalized/metrics.md). Aside from scan durations (which depend on host hardware), the classification metrics should match the baseline below:

| Tool | TP (Detected) | FN (Missed) | TN (Clean) | FP (False alarms) | Precision | Recall | F1-score | FPR | FNR | Avg time / file |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Checkov** (`3.4.5`) | 10 / 10 | 0 / 10 | 13 / 14 | 1 / 14 | 90.9% | 100.0% | 95.2% | 7.1% | 0.0% | 11.51s |
| **KICS** (`2.2.1`) | 8 / 10 | 2 / 10 | 14 / 14 | 0 / 14 | 100.0% | 80.0% | 88.9% | 0.0% | 20.0% | 7.89s |

Key observations from these results:
- **Checkov (`10/10` TP, `1` FP):** Detects all 10 vulnerable configurations (`100.0%` recall), including `EN-01-vulnerable.tf` (via `CKV_AWS_145`) and `ID-02-vulnerable.tf` (via its permissions-management check `CKV_AWS_289` and restrictable-wildcard-resource check `CKV_AWS_355`). It produces 1 false positive on `EN-01-fixed.tf` because `CKV_AWS_145` requires KMS encryption (`aws:kms`) and flags buckets configured with standard `AES256`.
- **KICS (`8/10` TP, `0` FP):** Produces zero false alarms on the 14 fixed and benign files (`100.0%` precision), but misses 2 vulnerable cases (`80.0%` recall): `EN-01-vulnerable.tf` (omitted S3 encryption companion resource) and `ID-02-vulnerable.tf` (where its PassRole queries inspect inline role policies or attached identity policies rather than a standalone `aws_iam_policy`).

---

## 7. Optional: Terraform Formatting Check

If Terraform CLI is installed on your machine, you can verify that all 24 benchmark files follow canonical HCL formatting:

```bash
terraform fmt -check -recursive benchmark/cases
```

When all files are properly formatted, the command exits with status code `0` and prints no output. No `terraform init` or cloud credentials are required because the benchmark performs static analysis only and never deploys cloud resources.

---

## 8. Optional: Building the PDF Report from Source

The pre-compiled final report is already included at [`docs/report/main.pdf`](report/main.pdf). If you modify the LaTeX source file ([`docs/report/main.tex`](report/main.tex)) and want to rebuild the PDF from scratch, make sure a LaTeX distribution providing `pdflatex` (such as MiKTeX) is installed and close `main.pdf` in any PDF viewer so the file is not locked.

**Windows (Command Prompt or PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File .\docs\report\build-report.ps1
```

**Linux / macOS (or manual compilation with `pdflatex` on `PATH`):**
```bash
cd docs/report
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```
