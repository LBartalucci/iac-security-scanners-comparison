import argparse
import csv
import datetime
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Default project paths relative to the repository root
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CASES_DIR = ROOT_DIR / "benchmark" / "cases"
DEFAULT_EXPECTED_PATH = ROOT_DIR / "benchmark" / "expected-results.json"
DEFAULT_RAW_DIR = ROOT_DIR / "results" / "raw"
DEFAULT_NORM_DIR = ROOT_DIR / "results" / "normalized"
DEFAULT_VERSIONS_PATH = ROOT_DIR / "scripts" / "docker-versions.env"


def read_docker_versions(path):
    # Read the pinned Checkov and KICS Docker image tags from scripts/docker-versions.env
    if not path.is_file():
        raise FileNotFoundError(f"Docker versions file not found at '{path}'.")
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip()
    return values


def get_case_filename(case):
    # Map a ground-truth record (id + type) to its corresponding .tf filename in benchmark/cases/
    case_id = case["id"]
    case_type = case["type"]
    if case_type == "benign":
        return f"{case_id}.tf"
    if case_type == "corrected":
        return f"{case_id}-fixed.tf"
    return f"{case_id}-{case_type}.tf"


def validate_hcl_dataset(cases_dir, expected_records):
    # Basic sanity check to make sure all expected .tf files exist and contain valid resource blocks
    tf_files = sorted(cases_dir.glob("*.tf"))
    if not tf_files:
        raise RuntimeError(f"No Terraform (.tf) files found in '{cases_dir}'.")

    expected_filenames = {get_case_filename(rec) for rec in expected_records}
    actual_filenames = {f.name for f in tf_files}

    missing = expected_filenames - actual_filenames
    if missing:
        raise RuntimeError(f"Missing expected Terraform files in '{cases_dir}': {sorted(missing)}")

    for tf_file in tf_files:
        content = tf_file.read_text(encoding="utf-8")
        if content.count("{") != content.count("}"):
            raise ValueError(f"Unbalanced braces in '{tf_file.name}'.")
        if not re.search(r'^\s*resource\s+"aws_[a-z0-9_]+"', content, re.MULTILINE):
            raise ValueError(f"No AWS resource block found in '{tf_file.name}'.")


def sanitize_raw_artifacts(raw_dir):
    # Replace local machine paths in the raw JSON reports with clean repository-relative paths
    meta_path = raw_dir / "run-metadata.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        meta["cases_path"] = "benchmark/cases"
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    checkov_dir = raw_dir / "checkov"
    if checkov_dir.is_dir():
        for jf in sorted(checkov_dir.glob("*.json")):
            data = json.loads(jf.read_text(encoding="utf-8-sig"))
            stem_tf = f"{jf.stem}.tf"
            rel_path = f"benchmark/cases/{stem_tf}"
            for check in data.get("results", {}).get("failed_checks", []):
                check["file_path"] = f"/{stem_tf}"
                check["file_abs_path"] = rel_path
                check["repo_file_path"] = f"/{rel_path}"
                check["definition_context_file_path"] = rel_path
                conn = check.get("connected_node")
                if isinstance(conn, dict):
                    conn["file_path"] = f"/{stem_tf}"
                    conn["file_abs_path"] = rel_path
            jf.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")

    kics_dir = raw_dir / "kics"
    if kics_dir.is_dir():
        for jf in sorted(kics_dir.glob("*/kics.json")):
            data = json.loads(jf.read_text(encoding="utf-8-sig"))
            stem_tf = f"{jf.parent.name}.tf"
            rel_path = f"benchmark/cases/{stem_tf}"
            data["paths"] = [rel_path]
            for query in data.get("queries", []):
                for f_entry in query.get("files", []):
                    f_entry["file_name"] = rel_path
            jf.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_scans(cases_dir, raw_dir, versions_path, docker_cmd="docker"):
    # Run Checkov and KICS inside Docker containers for each .tf file one by one
    versions = read_docker_versions(versions_path)
    checkov_image = versions.get("CHECKOV_IMAGE")
    kics_image = versions.get("KICS_IMAGE")
    if not checkov_image or not kics_image:
        raise ValueError(f"CHECKOV_IMAGE and KICS_IMAGE must be set in '{versions_path}'.")

    if not shutil.which(docker_cmd):
        raise RuntimeError(
            f"Docker executable '{docker_cmd}' was not found. "
            "Make sure Docker is running or pass '--skip-scan' to use existing raw files."
        )

    # Clear old raw outputs before starting a new scan
    checkov_out = raw_dir / "checkov"
    kics_out = raw_dir / "kics"
    if checkov_out.exists():
        shutil.rmtree(checkov_out)
    if kics_out.exists():
        shutil.rmtree(kics_out)
    checkov_out.mkdir(parents=True, exist_ok=True)
    kics_out.mkdir(parents=True, exist_ok=True)

    tf_files = sorted(cases_dir.glob("*.tf"))
    if not tf_files:
        raise RuntimeError(f"No Terraform files found in '{cases_dir}'.")

    checkov_seconds = 0.0
    kics_seconds = 0.0
    cases_abs = str(cases_dir.resolve())
    raw_abs = str(raw_dir.resolve())

    for tf_file in tf_files:
        stem = tf_file.stem
        print(f"Scanning {tf_file.name} with Checkov and KICS...")

        # 1. Run Checkov on the current Terraform file and measure elapsed time
        checkov_json_path = checkov_out / f"{stem}.json"
        t0 = time.perf_counter()
        proc_ckv = subprocess.run(
            [
                docker_cmd,
                "run",
                "--rm",
                "--volume",
                f"{cases_abs}:/workspace/cases:ro",
                checkov_image,
                "-f",
                f"/workspace/cases/{tf_file.name}",
                "--framework",
                "terraform",
                "--output",
                "json",
                "--quiet",
                "--soft-fail",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        checkov_seconds += time.perf_counter() - t0
        if proc_ckv.returncode != 0:
            raise RuntimeError(
                f"Checkov failed for '{tf_file.name}' (exit {proc_ckv.returncode}):\n{proc_ckv.stderr}"
            )
        checkov_json_path.write_text(proc_ckv.stdout, encoding="utf-8")

        # 2. Run KICS on the current Terraform file and measure elapsed time
        case_kics_out = kics_out / stem
        case_kics_out.mkdir(parents=True, exist_ok=True)
        t1 = time.perf_counter()
        proc_kics = subprocess.run(
            [
                docker_cmd,
                "run",
                "--rm",
                "--volume",
                f"{cases_abs}:/workspace/cases:ro",
                "--volume",
                f"{raw_abs}:/workspace/results",
                kics_image,
                "scan",
                "-p",
                f"/workspace/cases/{tf_file.name}",
                "-o",
                f"/workspace/results/kics/{stem}",
                "--output-name",
                "kics",
                "--report-formats",
                "json",
                "--ignore-on-exit",
                "results",
                "--silent",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        kics_seconds += time.perf_counter() - t1
        if proc_kics.returncode != 0:
            raise RuntimeError(
                f"KICS failed for '{tf_file.name}' (exit {proc_kics.returncode}):\n{proc_kics.stderr}"
            )
        if not (case_kics_out / "kics.json").is_file():
            raise RuntimeError(f"KICS did not produce a report for '{tf_file.name}'.")

    # Save total scan durations and file count in run-metadata.json
    metadata = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cases_path": "benchmark/cases",
        "terraform_files": len(tf_files),
        "checkov_seconds_total": round(checkov_seconds, 3),
        "kics_seconds_total": round(kics_seconds, 3),
    }
    (raw_dir / "run-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    sanitize_raw_artifacts(raw_dir)


def load_raw_findings(raw_dir):
    # Parse all raw Checkov and KICS JSON files into dictionaries indexed by the .tf filename
    checkov_by_file = {}
    kics_by_file = {}

    # Extract failed checks from each Checkov report
    checkov_dir = raw_dir / "checkov"
    if checkov_dir.is_dir():
        for report_path in sorted(checkov_dir.glob("*.json")):
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            tf_name = f"{report_path.stem}.tf"
            failed = report.get("results", {}).get("failed_checks", []) or []
            findings = []
            for item in failed:
                findings.append(
                    {
                        "Tool": "Checkov",
                        "FileName": tf_name,
                        "Name": item.get("check_name"),
                        "Severity": item.get("severity"),
                        "CheckId": item.get("check_id"),
                        "Resource": item.get("resource"),
                    }
                )
            checkov_by_file[tf_name] = findings

    # Extract triggered queries and affected files from each KICS report
    kics_dir = raw_dir / "kics"
    if kics_dir.is_dir():
        for report_path in sorted(kics_dir.glob("*/kics.json")):
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            tf_name = f"{report_path.parent.name}.tf"
            queries = report.get("queries", []) or []
            findings = []
            for q in queries:
                for f_obj in q.get("files", []) or []:
                    findings.append(
                        {
                            "Tool": "KICS",
                            "FileName": tf_name,
                            "Name": q.get("query_name"),
                            "Severity": q.get("severity"),
                            "CheckId": q.get("query_id"),
                            "Resource": f"{f_obj.get('resource_type', 'n/a')}.{f_obj.get('resource_name', 'n/a')}",
                        }
                    )
            kics_by_file[tf_name] = findings

    return checkov_by_file, kics_by_file


def deduplicate_findings(findings):
    # Group identical rules that fired multiple times on the same file (e.g. KICS port checks on NW-03)
    # and store how many times each rule occurred
    grouped = {}
    for f in findings:
        key = (str(f.get("CheckId") or ""), str(f.get("Name") or ""), f.get("Severity"))
        if key not in grouped:
            grouped[key] = {
                "Name": f.get("Name"),
                "Severity": f.get("Severity"),
                "CheckId": f.get("CheckId"),
                "Resource": f.get("Resource"),
                "Occurrences": 1,
            }
        else:
            grouped[key]["Occurrences"] += 1
    return sorted(grouped.values(), key=lambda x: (str(x["CheckId"]), str(x["Name"])))


def get_status(case_type, target_count):
    # For vulnerable files: a match means the vulnerability was detected (TP), no match means missed (FN).
    # For corrected/benign files: 0 matches means clean (TN), any match is a false alarm (FP).
    if case_type == "vulnerable":
        return "detected" if target_count > 0 else "missed-or-no-applicable-rule"
    return "clean" if target_count == 0 else "unexpected-targeted-finding"


def normalize_results(expected_path, raw_dir, norm_dir):
    # Compare raw findings against expected-results.json and write comparison.json, .csv, and .md
    expected_records = json.loads(expected_path.read_text(encoding="utf-8-sig"))
    checkov_by_file, kics_by_file = load_raw_findings(raw_dir)
    norm_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for case in expected_records:
        case_id = case["id"]
        case_type = case["type"]
        file_name = get_case_filename(case)

        # Ensure raw reports exist for every expected case
        if file_name not in checkov_by_file:
            raise FileNotFoundError(
                f"Missing Checkov raw report for '{file_name}' in '{raw_dir / 'checkov'}'."
            )
        if file_name not in kics_by_file:
            raise FileNotFoundError(
                f"Missing KICS raw report for '{file_name}' in '{raw_dir / 'kics'}'."
            )

        expected_ckv_ids = set(case.get("expected_checkov_id") or [])
        expected_kics_ids = set(case.get("expected_kics_id") or [])

        case_ckv_raw = checkov_by_file[file_name]
        case_kics_raw = kics_by_file[file_name]

        # Filter only the findings that match the expected rules for this specific test case
        target_ckv_raw = [f for f in case_ckv_raw if f["CheckId"] in expected_ckv_ids]
        target_kics_raw = [f for f in case_kics_raw if f["CheckId"] in expected_kics_ids]

        target_ckv = deduplicate_findings(target_ckv_raw)
        target_kics = deduplicate_findings(target_kics_raw)
        all_ckv = deduplicate_findings(case_ckv_raw)
        all_kics = deduplicate_findings(case_kics_raw)

        rec = {
            "Id": case_id,
            "Type": case_type,
            "Category": case["category"],
            "File": f"benchmark/cases/{file_name}",
            "ExpectedIssue": case["expected_issue"],
            "StructuralPattern": case.get("structural_pattern", ""),
            "CheckovStatus": get_status(case_type, len(target_ckv)),
            "KicsStatus": get_status(case_type, len(target_kics)),
            "CheckovTargetedRuleCount": len(target_ckv),
            "KicsTargetedRuleCount": len(target_kics),
            "CheckovTargetedInstanceCount": len(target_ckv_raw),
            "KicsTargetedInstanceCount": len(target_kics_raw),
            "CheckovTargetedFindings": target_ckv,
            "KicsTargetedFindings": target_kics,
            "CheckovUniqueRuleCount": len(all_ckv),
            "KicsUniqueRuleCount": len(all_kics),
            "CheckovAllFindingCount": len(case_ckv_raw),
            "KicsAllFindingCount": len(case_kics_raw),
            "CheckovNonTargetFindingCount": len(case_ckv_raw) - len(target_ckv_raw),
            "KicsNonTargetFindingCount": len(case_kics_raw) - len(target_kics_raw),
            "CheckovAllFindings": all_ckv,
            "KicsAllFindings": all_kics,
        }
        if "disagreement_reason" in case:
            rec["DisagreementReason"] = case["disagreement_reason"]
        if "risk_profile" in case:
            rec["RiskProfile"] = case["risk_profile"]
        records.append(rec)

    # Save full normalized data as JSON
    (norm_dir / "comparison.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )

    # Save tabular summary as CSV
    csv_fields = [
        "Id",
        "Type",
        "Category",
        "File",
        "ExpectedIssue",
        "CheckovStatus",
        "KicsStatus",
        "CheckovTargetedRuleCount",
        "KicsTargetedRuleCount",
        "CheckovUniqueRuleCount",
        "KicsUniqueRuleCount",
        "CheckovAllFindingCount",
        "KicsAllFindingCount",
    ]
    with (norm_dir / "comparison.csv").open("w", encoding="utf-8", newline="") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=csv_fields, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r[k] for k in csv_fields})

    # Build readable Markdown comparison report (comparison.md)
    md_lines = [
        "## Normalized comparison",
        "",
        "| Tool | Vulnerable detected (TP) | Vulnerable missed (FN) | Corrected clean | Corrected false alarm (FP) | Benign clean |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for tool, prop in [("Checkov", "CheckovStatus"), ("KICS", "KicsStatus")]:
        vuln = [r for r in records if r["Type"] == "vulnerable"]
        corr = [r for r in records if r["Type"] == "corrected"]
        ben = [r for r in records if r["Type"] == "benign"]
        tp = sum(1 for r in vuln if r[prop] == "detected")
        fn = sum(1 for r in vuln if r[prop] == "missed-or-no-applicable-rule")
        corr_clean = sum(1 for r in corr if r[prop] == "clean")
        corr_fp = sum(1 for r in corr if r[prop] == "unexpected-targeted-finding")
        ben_clean = sum(1 for r in ben if r[prop] == "clean")
        md_lines.append(
            f"| {tool} | {tp} / {len(vuln)} | {fn} / {len(vuln)} | {corr_clean} / {len(corr)} | {corr_fp} / {len(corr)} | {ben_clean} / {len(ben)} |"
        )

    md_lines.extend(
        [
            "",
            "### Case-by-case detection and signal-to-noise breakdown",
            "",
            "| Case | Type | Category | Checkov Status | KICS Status | Checkov Targeted / Total | KICS Targeted / Total (Unique Rules) |",
            "|---|---|---|---|---|---:|---:|",
        ]
    )
    for r in records:
        md_lines.append(
            f"| `{r['Id']}` | {r['Type']} | `{r['Category']}` | `{r['CheckovStatus']}` | `{r['KicsStatus']}` | "
            f"{r['CheckovTargetedInstanceCount']} / {r['CheckovAllFindingCount']} | "
            f"{r['KicsTargetedInstanceCount']} / {r['KicsAllFindingCount']} ({r['KicsUniqueRuleCount']} rules) |"
        )

    disagreements = [r for r in records if r.get("DisagreementReason")]
    if disagreements:
        md_lines.extend(
            [
                "",
                "### Tool disagreements and root-cause analysis",
                "",
                "| Case | Type | Checkov | KICS | Root Cause |",
                "|---|---|---|---|---|",
            ]
        )
        for r in disagreements:
            md_lines.append(
                f"| `{r['Id']}` | {r['Type']} | `{r['CheckovStatus']}` | `{r['KicsStatus']}` | {r['DisagreementReason']} |"
            )

    md_lines.extend(
        [
            "",
            "Statuses are evaluated against the expected rule definitions in `benchmark/expected-results.json` via `scripts/benchmark.py`.",
        ]
    )
    (norm_dir / "comparison.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return records


def format_pct(val):
    if val is None:
        return "n/a"
    return f"{round(val * 100, 1)}%"


def build_metrics(records, raw_dir, norm_dir):
    # Compute Precision, Recall, F1, FPR, FNR, per-category recall, alert noise, and scan timings
    meta_path = raw_dir / "run-metadata.json"
    meta = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))

    tf_count = meta.get("terraform_files", len(records))
    timings = {
        "Checkov": {
            "total_seconds": meta.get("checkov_seconds_total"),
            "avg_seconds_per_file": round(meta["checkov_seconds_total"] / tf_count, 3)
            if meta.get("checkov_seconds_total") and tf_count
            else None,
        },
        "KICS": {
            "total_seconds": meta.get("kics_seconds_total"),
            "avg_seconds_per_file": round(meta["kics_seconds_total"] / tf_count, 3)
            if meta.get("kics_seconds_total") and tf_count
            else None,
        },
    }

    metrics = []
    for tool in ["Checkov", "KICS"]:
        prefix = "Checkov" if tool == "Checkov" else "Kics"
        status_prop = f"{prefix}Status"

        vuln = [r for r in records if r["Type"] == "vulnerable"]
        corr = [r for r in records if r["Type"] == "corrected"]
        ben = [r for r in records if r["Type"] == "benign"]

        # Confusion matrix counts:
        # TP = vulnerable detected, FN = vulnerable missed
        # FP = unexpected targeted finding on corrected/benign, TN = clean corrected/benign
        tp = sum(1 for r in vuln if r[status_prop] == "detected")
        fn = sum(1 for r in vuln if r[status_prop] == "missed-or-no-applicable-rule")
        fp_corr = sum(1 for r in corr if r[status_prop] == "unexpected-targeted-finding")
        fp_ben = sum(1 for r in ben if r[status_prop] == "unexpected-targeted-finding")
        fp = fp_corr + fp_ben
        tn_corr = sum(1 for r in corr if r[status_prop] == "clean")
        tn_ben = sum(1 for r in ben if r[status_prop] == "clean")
        tn = tn_corr + tn_ben

        # Standard classification formulas
        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None
        recall = round(tp / len(vuln), 4) if vuln else None
        f1 = (
            round((2 * precision * recall) / (precision + recall), 4)
            if (precision is not None and recall is not None and (precision + recall) > 0)
            else None
        )
        fnr = round(fn / (tp + fn), 4) if (tp + fn) > 0 else None
        fpr = round(fp / (fp + tn), 4) if (fp + tn) > 0 else None

        # Signal-to-noise calculations (targeted findings vs. unrelated best-practice findings)
        total_instances = sum(r[f"{prefix}AllFindingCount"] for r in records)
        total_unique_rules = sum(r[f"{prefix}UniqueRuleCount"] for r in records)
        targeted_instances = sum(r[f"{prefix}TargetedInstanceCount"] for r in vuln)
        targeted_unique_rules = sum(r[f"{prefix}TargetedRuleCount"] for r in vuln)
        non_target_instances = total_instances - sum(
            r[f"{prefix}TargetedInstanceCount"] for r in records
        )
        non_target_unique_rules = total_unique_rules - sum(
            r[f"{prefix}TargetedRuleCount"] for r in records
        )
        snr_instances = round(targeted_instances / total_instances, 4) if total_instances > 0 else 0.0
        snr_unique_rules = (
            round(targeted_unique_rules / total_unique_rules, 4) if total_unique_rules > 0 else 0.0
        )

        metrics.append(
            {
                "Tool": tool,
                "TruePositives": tp,
                "FalseNegatives": fn,
                "TrueNegatives": tn,
                "FalsePositives": fp,
                "VulnerableDetected": tp,
                "VulnerableTotal": len(vuln),
                "VulnerableUnmatched": fn,
                "DetectionCoverage": recall,
                "Recall": recall,
                "BenchmarkTargetPrecision": precision,
                "F1Score": f1,
                "FalsePositiveRate": fpr,
                "FalseNegativeRate": fnr,
                "CorrectedClean": tn_corr,
                "CorrectedTotal": len(corr),
                "BenignClean": tn_ben,
                "BenignTotal": len(ben),
                "UnexpectedCorrectedFindings": fp_corr,
                "UnexpectedBenignFindings": fp_ben,
                "TotalFindingInstancesAcrossDataset": total_instances,
                "TotalUniqueRuleTriggersAcrossDataset": total_unique_rules,
                "TargetedFindingInstancesOnVulnerable": targeted_instances,
                "TargetedUniqueRulesOnVulnerable": targeted_unique_rules,
                "BackgroundNoiseFindingInstances": non_target_instances,
                "BackgroundNoiseUniqueRules": non_target_unique_rules,
                "SignalToNoiseRatioInstances": snr_instances,
                "SignalToNoiseRatioUniqueRules": snr_unique_rules,
                "TotalScanSeconds": timings[tool]["total_seconds"],
                "AvgSecondsPerFile": timings[tool]["avg_seconds_per_file"],
            }
        )

    # Calculate detection recall and false positives for each of the 4 misconfiguration categories
    categories = [
        "public-storage",
        "encryption-at-rest",
        "identity-permissions",
        "network-exposure",
    ]
    category_breakdown = []
    for cat in categories:
        cat_vuln = [r for r in records if r["Category"] == cat and r["Type"] == "vulnerable"]
        cat_corr = [r for r in records if r["Category"] == cat and r["Type"] == "corrected"]
        cat_ben = [r for r in records if r["Category"] == cat and r["Type"] == "benign"]

        ckv_tp = sum(1 for r in cat_vuln if r["CheckovStatus"] == "detected")
        kics_tp = sum(1 for r in cat_vuln if r["KicsStatus"] == "detected")
        ckv_fp = sum(
            1
            for r in (cat_corr + cat_ben)
            if r["CheckovStatus"] == "unexpected-targeted-finding"
        )
        kics_fp = sum(
            1
            for r in (cat_corr + cat_ben)
            if r["KicsStatus"] == "unexpected-targeted-finding"
        )

        category_breakdown.append(
            {
                "Category": cat,
                "VulnerableCases": len(cat_vuln),
                "CheckovDetected": ckv_tp,
                "CheckovRecall": round(ckv_tp / len(cat_vuln), 4) if cat_vuln else None,
                "CheckovFalsePositives": ckv_fp,
                "KicsDetected": kics_tp,
                "KicsRecall": round(kics_tp / len(cat_vuln), 4) if cat_vuln else None,
                "KicsFalsePositives": kics_fp,
            }
        )

    # Count KICS findings by severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)
    severity_levels = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    severity_counts = []
    for sev in severity_levels:
        targeted_unique_count = sum(
            1
            for r in records
            if r["Type"] == "vulnerable"
            for f in r["KicsTargetedFindings"]
            if f.get("Severity") == sev
        )
        targeted_instance_count = sum(
            f.get("Occurrences", 1)
            for r in records
            if r["Type"] == "vulnerable"
            for f in r["KicsTargetedFindings"]
            if f.get("Severity") == sev
        )
        all_instance_count = sum(
            f.get("Occurrences", 1)
            for r in records
            for f in r["KicsAllFindings"]
            if f.get("Severity") == sev
        )
        severity_counts.append(
            {
                "Tool": "KICS",
                "Severity": sev,
                "TargetedUniqueRuleCount": targeted_unique_count,
                "TargetedInstanceCount": targeted_instance_count,
                "AllDatasetInstanceCount": all_instance_count,
            }
        )

    result_obj = {
        "Metrics": metrics,
        "CategoryBreakdown": category_breakdown,
        "KicsSeverityCounts": severity_counts,
        "ExecutionMetadata": meta,
    }
    (norm_dir / "metrics.json").write_text(
        json.dumps(result_obj, indent=2) + "\n", encoding="utf-8"
    )

    # Write the Markdown summary tables to results/normalized/metrics.md
    lines = [
        "## Final benchmark metrics",
        "",
        "### Classification performance against ground-truth baseline",
        "",
        "| Tool | TP (Detected) | FN (Missed) | TN (Clean) | FP (False alarms) | Precision | Recall | F1-score | FPR | FNR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['Tool']} | {m['TruePositives']} / {m['VulnerableTotal']} | "
            f"{m['FalseNegatives']} / {m['VulnerableTotal']} | "
            f"{m['TrueNegatives']} / {m['CorrectedTotal'] + m['BenignTotal']} | "
            f"{m['FalsePositives']} / {m['CorrectedTotal'] + m['BenignTotal']} | "
            f"{format_pct(m['BenchmarkTargetPrecision'])} | "
            f"{format_pct(m['Recall'])} | "
            f"{format_pct(m['F1Score'])} | "
            f"{format_pct(m['FalsePositiveRate'])} | "
            f"{format_pct(m['FalseNegativeRate'])} |"
        )

    lines.extend(
        [
            "",
            "### Detection coverage and false alarms by category",
            "",
            "| Category | Vulnerable cases | Checkov detected (Recall) | Checkov FP | KICS detected (Recall) | KICS FP |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for c in category_breakdown:
        lines.append(
            f"| `{c['Category']}` | {c['VulnerableCases']} | "
            f"{c['CheckovDetected']} / {c['VulnerableCases']} ({format_pct(c['CheckovRecall'])}) | "
            f"{c['CheckovFalsePositives']} | "
            f"{c['KicsDetected']} / {c['VulnerableCases']} ({format_pct(c['KicsRecall'])}) | "
            f"{c['KicsFalsePositives']} |"
        )

    lines.extend(
        [
            "",
            "### Operational noise, alert volume, and execution time",
            "",
            "| Tool | Targeted unique rules (instances) | Background noise rules (instances) | Total unique rules (instances) | Rule SNR (Instance SNR) | Total scan time (s) | Avg time per file (s) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for m in metrics:
        tot_s = f"{m['TotalScanSeconds']:.3f}s" if m["TotalScanSeconds"] is not None else "n/a"
        avg_s = f"{m['AvgSecondsPerFile']:.2f}s" if m["AvgSecondsPerFile"] is not None else "n/a"
        lines.append(
            f"| {m['Tool']} | {m['TargetedUniqueRulesOnVulnerable']} ({m['TargetedFindingInstancesOnVulnerable']}) | "
            f"{m['BackgroundNoiseUniqueRules']} ({m['BackgroundNoiseFindingInstances']}) | "
            f"{m['TotalUniqueRuleTriggersAcrossDataset']} ({m['TotalFindingInstancesAcrossDataset']}) | "
            f"{format_pct(m['SignalToNoiseRatioUniqueRules'])} ({format_pct(m['SignalToNoiseRatioInstances'])}) | "
            f"{tot_s} | {avg_s} |"
        )

    lines.extend(
        [
            "",
            "### KICS severity distribution",
            "",
            "| Severity | Targeted unique rules (vulnerable cases) | Targeted finding instances | All dataset finding instances |",
            "|---|---:|---:|---:|",
        ]
    )
    for s in severity_counts:
        lines.append(
            f"| {s['Severity']} | {s['TargetedUniqueRuleCount']} | {s['TargetedInstanceCount']} | {s['AllDatasetInstanceCount']} |"
        )

    lines.extend(
        [
            "",
            "Checkov CLI output does not include severity values without an API key (`\"severity\": null`), so its severity distribution is not available.",
        ]
    )

    (norm_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result_obj


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Checkov and KICS benchmark scans and generate normalized comparison tables."
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="Skip Docker scans and compute results from existing files in results/raw/.",
    )
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument("--expected-path", type=Path, default=DEFAULT_EXPECTED_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--norm-dir", type=Path, default=DEFAULT_NORM_DIR)
    parser.add_argument("--versions-path", type=Path, default=DEFAULT_VERSIONS_PATH)
    parser.add_argument("--docker-cmd", type=str, default="docker")
    return parser.parse_args()


def main():
    args = parse_args()
    expected_records = json.loads(args.expected_path.read_text(encoding="utf-8-sig"))

    print("[1/4] Checking Terraform files...")
    validate_hcl_dataset(args.cases_dir, expected_records)

    if not args.skip_scan:
        print("[2/4] Running Checkov and KICS scans via Docker...")
        run_scans(args.cases_dir, args.raw_dir, args.versions_path, args.docker_cmd)
    else:
        print("[2/4] Skipping Docker scans (--skip-scan)...")

    print("[3/4] Normalizing results...")
    records = normalize_results(args.expected_path, args.raw_dir, args.norm_dir)

    print("[4/4] Building metrics...")
    build_metrics(records, args.raw_dir, args.norm_dir)

    print(f"Done. Results saved in {args.norm_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
