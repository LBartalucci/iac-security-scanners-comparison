## Normalized comparison

| Tool | Vulnerable detected (TP) | Vulnerable missed (FN) | Corrected clean | Corrected false alarm (FP) | Benign clean |
|---|---:|---:|---:|---:|---:|
| Checkov | 10 / 10 | 0 / 10 | 9 / 10 | 1 / 10 | 4 / 4 |
| KICS | 8 / 10 | 2 / 10 | 10 / 10 | 0 / 10 | 4 / 4 |

### Case-by-case detection and signal-to-noise breakdown

| Case | Type | Category | Checkov Status | KICS Status | Checkov Targeted / Total | KICS Targeted / Total (Unique Rules) |
|---|---|---|---|---|---:|---:|
| `ST-01` | vulnerable | `public-storage` | `detected` | `detected` | 2 / 8 | 1 / 5 (5 rules) |
| `ST-02` | vulnerable | `public-storage` | `detected` | `detected` | 5 / 11 | 3 / 7 (7 rules) |
| `ST-03` | vulnerable | `public-storage` | `detected` | `detected` | 2 / 8 | 2 / 7 (7 rules) |
| `EN-01` | vulnerable | `encryption-at-rest` | `detected` | `missed-or-no-applicable-rule` | 1 / 7 | 0 / 4 (4 rules) |
| `EN-02` | vulnerable | `encryption-at-rest` | `detected` | `detected` | 1 / 2 | 1 / 3 (3 rules) |
| `ID-01` | vulnerable | `identity-permissions` | `detected` | `detected` | 9 / 9 | 3 / 6 (6 rules) |
| `ID-02` | vulnerable | `identity-permissions` | `detected` | `missed-or-no-applicable-rule` | 2 / 2 | 0 / 2 (2 rules) |
| `NW-01` | vulnerable | `network-exposure` | `detected` | `detected` | 1 / 3 | 3 / 8 (8 rules) |
| `NW-02` | vulnerable | `network-exposure` | `detected` | `detected` | 1 / 3 | 3 / 8 (8 rules) |
| `NW-03` | vulnerable | `network-exposure` | `detected` | `detected` | 4 / 6 | 129 / 137 (12 rules) |
| `ST-01` | corrected | `public-storage` | `clean` | `clean` | 0 / 6 | 0 / 4 (4 rules) |
| `ST-02` | corrected | `public-storage` | `clean` | `clean` | 0 / 6 | 0 / 4 (4 rules) |
| `ST-03` | corrected | `public-storage` | `clean` | `clean` | 0 / 6 | 0 / 4 (4 rules) |
| `EN-01` | corrected | `encryption-at-rest` | `unexpected-targeted-finding` | `clean` | 1 / 7 | 0 / 4 (4 rules) |
| `EN-02` | corrected | `encryption-at-rest` | `clean` | `clean` | 0 / 1 | 0 / 2 (2 rules) |
| `ID-01` | corrected | `identity-permissions` | `clean` | `clean` | 0 / 0 | 0 / 2 (2 rules) |
| `ID-02` | corrected | `identity-permissions` | `clean` | `clean` | 0 / 0 | 0 / 2 (2 rules) |
| `NW-01` | corrected | `network-exposure` | `clean` | `clean` | 0 / 2 | 0 / 6 (6 rules) |
| `NW-02` | corrected | `network-exposure` | `clean` | `clean` | 0 / 2 | 0 / 6 (6 rules) |
| `NW-03` | corrected | `network-exposure` | `clean` | `clean` | 0 / 2 | 0 / 6 (6 rules) |
| `BC-01` | benign | `public-storage` | `clean` | `clean` | 0 / 6 | 0 / 4 (4 rules) |
| `BC-02` | benign | `encryption-at-rest` | `clean` | `clean` | 0 / 1 | 0 / 2 (2 rules) |
| `BC-03` | benign | `identity-permissions` | `clean` | `clean` | 0 / 0 | 0 / 2 (2 rules) |
| `BC-04` | benign | `network-exposure` | `clean` | `clean` | 0 / 2 | 0 / 6 (6 rules) |

### Tool disagreements and root-cause analysis

| Case | Type | Checkov | KICS | Root Cause |
|---|---|---|---|---|
| `EN-01` | vulnerable | `detected` | `missed-or-no-applicable-rule` | Checkov flags the bucket with CKV_AWS_145 (which requires explicit aws:kms encryption on every aws_s3_bucket and fires whenever KMS encryption is absent); KICS does not flag an aws_s3_bucket that omits the separate server-side encryption resource. |
| `ID-02` | vulnerable | `detected` | `missed-or-no-applicable-rule` | Checkov flags standalone aws_iam_policy resources granting iam:PassRole on Resource '*' via its permissions-management (CKV_AWS_289) and restrictable-wildcard-resource (CKV_AWS_355) checks; KICS's PassRole queries target inline role policies or attached identity policies rather than a standalone unattached aws_iam_policy. |
| `EN-01` | corrected | `unexpected-targeted-finding` | `clean` | Checkov reports a False Positive on EN-01-fixed.tf because rule CKV_AWS_145 requires KMS encryption (aws:kms) and does not accept standard AES256 server-side encryption. |

Statuses are evaluated against the expected rule definitions in `benchmark/expected-results.json` via `scripts/benchmark.py`.
