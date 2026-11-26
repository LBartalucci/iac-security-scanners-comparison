## Final benchmark metrics

### Classification performance against ground-truth baseline

| Tool | TP (Detected) | FN (Missed) | TN (Clean) | FP (False alarms) | Precision | Recall | F1-score | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Checkov | 10 / 10 | 0 / 10 | 13 / 14 | 1 / 14 | 90.9% | 100.0% | 95.2% | 7.1% | 0.0% |
| KICS | 8 / 10 | 2 / 10 | 14 / 14 | 0 / 14 | 100.0% | 80.0% | 88.9% | 0.0% | 20.0% |

### Detection coverage and false alarms by category

| Category | Vulnerable cases | Checkov detected (Recall) | Checkov FP | KICS detected (Recall) | KICS FP |
|---|---:|---:|---:|---:|---:|
| `public-storage` | 3 | 3 / 3 (100.0%) | 0 | 3 / 3 (100.0%) | 0 |
| `encryption-at-rest` | 2 | 2 / 2 (100.0%) | 1 | 1 / 2 (50.0%) | 0 |
| `identity-permissions` | 2 | 2 / 2 (100.0%) | 0 | 1 / 2 (50.0%) | 0 |
| `network-exposure` | 3 | 3 / 3 (100.0%) | 0 | 3 / 3 (100.0%) | 0 |

### Operational noise, alert volume, and execution time

| Tool | Targeted unique rules (instances) | Background noise rules (instances) | Total unique rules (instances) | Rule SNR (Instance SNR) | Total scan time (s) | Avg time per file (s) |
|---|---:|---:|---:|---:|---:|---:|
| Checkov | 28 (28) | 71 (71) | 100 (100) | 28.0% (28.0%) | 276.299s | 11.51s |
| KICS | 20 (145) | 96 (96) | 116 (241) | 17.2% (60.2%) | 189.335s | 7.89s |

### KICS severity distribution

| Severity | Targeted unique rules (vulnerable cases) | Targeted finding instances | All dataset finding instances |
|---|---:|---:|---:|
| CRITICAL | 2 | 2 | 2 |
| HIGH | 11 | 136 | 137 |
| MEDIUM | 7 | 7 | 28 |
| LOW | 0 | 0 | 29 |
| INFO | 0 | 0 | 45 |

Checkov CLI output does not include severity values without an API key (`"severity": null`), so its severity distribution is not available.
