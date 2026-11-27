# Experimental Comparison of Checkov and KICS for Terraform Security Misconfiguration Detection

## 1. Introduction

This project was developed for the **ICT Risk Assessment** university course.

Infrastructure-as-Code (IaC) allows engineering teams to provision cloud infrastructure through configuration files such as Terraform. However, misconfigurations in Terraform templates - such as publicly exposed storage buckets, missing encryption, overprivileged IAM policies, or unrestricted firewall rules - translate directly into cloud security vulnerabilities if deployed.

This repository contains a reproducible benchmark comparing two open-source IaC static-analysis tools:

- **[Checkov](https://github.com/bridgecrewio/checkov)** (`v3.4.5`): Combines Python attribute checks with a cross-resource graph engine that connects separate Terraform resources.
- **[KICS](https://github.com/Checkmarx/kics)** (`v2.2.1`): Evaluates parsed Terraform files using Open Policy Agent (OPA) Rego queries.

### Why this is useful

Static scanners use different rule definitions and detection approaches. Relying on a single scanner without knowing its limitations introduces two main problems during risk assessment:
1. **Undetected vulnerabilities (False Negatives)**: Missing a real misconfiguration leaves security risks in the infrastructure.
2. **False alarms and alert noise (False Positives & Noise)**: Overly strict rules or hundreds of repeated alerts for a single resource can waste remediation effort and make it harder to prioritize real risks.

To evaluate these differences without deploying cloud resources, both tools are tested on a manually verified dataset of **24 Terraform configurations** (10 vulnerable cases, 10 fixed counterparts, and 4 safe control cases) across four categories:
- **Public cloud storage** (`ST-01` to `ST-03`, `BC-01`)
- **Missing encryption at rest** (`EN-01` to `EN-02`, `BC-02`)
- **Excessive identity permissions** (`ID-01` to `ID-02`, `BC-03`)
- **Unrestricted network access** (`NW-01` to `NW-03`, `BC-04`)

A complete description of all 24 test cases, what each vulnerability does, and how the fixed versions resolve them can be found in [`benchmark/TEST-CASES.md`](benchmark/TEST-CASES.md).

---

## 2. Repository Structure

```text
├── benchmark/
│   ├── cases/
│   ├── TEST-CASES.md
│   └── expected-results.json
├── scripts/
│   ├── benchmark.py
│   └── docker-versions.env
├── results/
│   ├── raw/
│   └── normalized/
└── docs/
    ├── testing-guide.md
    └── report/
```

- **`benchmark/`**: Contains the 24 Terraform test configurations (`cases/`), a detailed explanation of each test case ([`TEST-CASES.md`](benchmark/TEST-CASES.md)), and the ground-truth baseline ([`expected-results.json`](benchmark/expected-results.json)) with the expected rule IDs and risk descriptions.
- **`scripts/`**: Contains the Python 3 benchmark script ([`benchmark.py`](scripts/benchmark.py)) and the pinned Docker image tags ([`docker-versions.env`](scripts/docker-versions.env)).
- **`results/`**: Stores the raw JSON outputs from Checkov and KICS along with scan duration metadata (`raw/`), and the normalized comparisons and metric tables in Markdown, CSV, and JSON formats (`normalized/`).
- **`docs/`**: Contains the testing guide ([`testing-guide.md`](docs/testing-guide.md)) and the final project report source and PDF (`report/`).

---

## 3. How to Test for Yourself

The benchmark pipeline is written in a single Python 3 script ([`scripts/benchmark.py`](scripts/benchmark.py)) using only the standard library (no external packages or virtual environment needed).

### Requirements

- **Python 3.8+**
- **Docker** (used to run the pinned `bridgecrew/checkov:3.4.5` and `checkmarx/kics:v2.2.1` containers)

### Command

Run the benchmark from the repository root:

```bash
python scripts/benchmark.py
```

When executed, `scripts/benchmark.py` runs each tool in isolation on the 24 Terraform files, saves the raw JSON outputs into `results/raw/`, and compares those findings against the expected rule IDs in `benchmark/expected-results.json`. It then automatically generates the normalized output files in `results/normalized/`, including two main readable summaries:

- **[`results/normalized/comparison.md`](results/normalized/comparison.md)**: Contains the case-by-case results across all 24 Terraform files, showing whether each configuration was marked as `detected`, `missed-or-no-applicable-rule`, `clean`, or `unexpected-targeted-finding`, along with the ratio of targeted alerts to total alerts and the reasons behind tool differences.
- **[`results/normalized/metrics.md`](results/normalized/metrics.md)**: Aggregates the case-level results into overall classification metrics (`TP`, `FN`, `TN`, `FP`, Precision, Recall, F1-score, FPR, and FNR), per-category detection coverage, operational signal-to-noise ratios, KICS severity counts, and scan execution times.

### Expected Results and Main Findings

| Tool | TP (Vulnerable detected) | FN (Missed) | TN (Clean controls) | FP (False alarms) | Precision | Recall | F1-score | FPR | FNR | Avg time / file |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Checkov** (`3.4.5`) | 10 / 10 | 0 / 10 | 13 / 14 | 1 / 14 | 90.9% | 100.0% | 95.2% | 7.1% | 0.0% | 11.51s |
| **KICS** (`2.2.1`) | 8 / 10 | 2 / 10 | 14 / 14 | 0 / 14 | 100.0% | 80.0% | 88.9% | 0.0% | 20.0% | 7.89s |

The experiment highlights three main findings (discussed in detail in the final report in [`docs/report/`](docs/report/)):

1. **Detection Coverage (Recall) vs. Rule Strictness (Precision)**: Checkov achieved **100% recall** (`10/10` vulnerable configurations detected), whereas KICS detected `8/10`. However, Checkov produced **1 false positive** (`90.9%` precision) on `EN-01-fixed.tf` because its S3 encryption rule (`CKV_AWS_145`) requires KMS encryption (`aws:kms`) on every bucket and flags buckets configured with standard `AES256` encryption.
2. **Missed Detections in KICS**: KICS achieved **100% precision** (`0` false alarms on fixed and benign cases), but missed **2 vulnerable cases** (`EN-01` and `ID-02`). In `EN-01`, KICS did not flag the S3 bucket when the separate server-side encryption companion resource was omitted. In `ID-02`, Checkov flagged the standalone `aws_iam_policy` granting `iam:PassRole` on `Resource = "*"` through its permissions-management (`CKV_AWS_289`) and restrictable-wildcard-resource (`CKV_AWS_355`) checks, whereas KICS's PassRole queries target inline role policies or attached identity policies rather than a standalone unattached `aws_iam_policy`.
3. **Alert Volume and Noise**: Both tools report several general best-practice warnings (such as missing tags, access logging, or versioning) in addition to the targeted security issue. On `NW-03-vulnerable.tf` (where all ports and protocols are open to `0.0.0.0/0`), KICS outputs 137 findings for a single 10-line resource (including 126 instances of query `381c3f2a`) because it checks the open range against every port in its sensitive-port list one by one.

---

## Author

**Lorenzo Bartalucci** - Student ID: `655671` (GitHub: [@LBartalucci](https://github.com/LBartalucci))
