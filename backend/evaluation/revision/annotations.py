"""Blinded human response annotation and conservative, auditable aggregation.

This module never assigns clinical labels. Its only inputs are frozen runner JSONL,
a private export mapping, and an explicitly completed human annotation CSV.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CONDITIONS = ("V", "V_L", "V_G", "V_GL")
CORE_CONDITIONS = ("V", "V_L", "V_G")
ERROR_FIELDS = ("unsupported_claim", "procedural_error", "critical_omission")
IDENTITY_FIELDS = ("annotation_id", "question", "answer", "evidence")
LABEL_FIELDS = (*ERROR_FIELDS, "correct", "supported_claims", "total_claims")
CSV_FIELDS = (*IDENTITY_FIELDS, "annotator_id", *LABEL_FIELDS, "comments")
SCHEMA_VERSION = 1


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _expected_conditions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value or any(not isinstance(item, str) for item in value):
        raise ValueError("Expected conditions must be a nonempty list of condition names")
    if len(set(value)) != len(value) or set(value) - set(CONDITIONS):
        raise ValueError("Expected conditions must be unique names from V,V_L,V_G,V_GL")
    return tuple(value)


def load_run(path: str | Path) -> list[dict[str, Any]]:
    """Read runner records, rejecting duplicate cases and ambiguous statuses."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    query_splits: dict[str, str] = {}
    query_questions: dict[str, str] = {}
    with Path(path).open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Run line {line_number} must be an object")
            query_id, condition, split = (row.get(name) for name in ("query_id", "condition", "split"))
            if not all(isinstance(value, str) and value.strip() for value in (query_id, condition, split)):
                raise ValueError(f"Run line {line_number} requires nonempty query_id, condition and split strings")
            if condition not in CONDITIONS:
                raise ValueError(f"Unknown condition {condition!r} at line {line_number}")
            if row.get("status") not in ("answered", "abstained", "error"):
                raise ValueError(f"Invalid status at line {line_number}")
            key = (query_id, condition)
            if key in seen:
                raise ValueError(f"Duplicate query/condition: {key}")
            seen.add(key)
            if query_id in query_splits and query_splits[query_id] != split:
                raise ValueError(f"Query {query_id!r} occurs in more than one split")
            query_splits[query_id] = split
            if row["status"] == "answered":
                _blinded_content(row)  # Enforce enough information for a human to judge.
            question = row.get("question", row.get("query"))
            if isinstance(question, str) and question.strip():
                if query_id in query_questions and query_questions[query_id] != question:
                    raise ValueError(f"Question text changes between conditions for {query_id!r}")
                query_questions[query_id] = question
            rows.append(row)
    if not rows:
        raise ValueError("The run contains no records")
    # Reject non-finite numerical values anywhere before freezing the run digest.
    _json(rows)
    return rows


def _run_digest(rows: list[dict[str, Any]]) -> str:
    ordered = sorted(rows, key=lambda row: (row["query_id"], row["condition"]))
    return hashlib.sha256(_json(ordered).encode("utf-8")).hexdigest()


def _blinded_content(row: dict[str, Any]) -> dict[str, str]:
    question = row.get("question", row.get("query"))
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"Answered query {row.get('query_id')!r} needs question text")
    answer = row.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"Answered query {row.get('query_id')!r} needs a nonempty answer")
    evidence = row.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("Answered records require an evidence list (possibly empty)")
    blinded_evidence = []
    for index, item in enumerate(evidence, 1):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ValueError("Every evidence item requires text")
        source = item.get("source", "")
        if not isinstance(source, str):
            raise ValueError("Evidence source must be a string")
        chunk_id = item.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("Evidence needs a neutral chunk_id so reviewers can resolve answer citations")
        blinded_evidence.append({"label": f"E{index}", "chunk_id": chunk_id, "source": source, "text": item["text"]})
    return {"question": question, "answer": answer, "evidence": _json(blinded_evidence)}


def export_annotations(
    run_path: str | Path,
    output_csv: str | Path,
    mapping_path: str | Path,
    *,
    seed: int = 2026,
    expected_conditions: tuple[str, ...] | list[str] = CORE_CONDITIONS,
) -> dict[str, Any]:
    """Create a shuffled blank rating sheet and a separate private mapping.

    Only answered responses are rated. Abstentions and infrastructure failures remain
    in the frozen run and in report denominators. Existing outputs are not overwritten.
    """
    run_path, output_csv, mapping_path = map(Path, (run_path, output_csv, mapping_path))
    paths = [path.resolve() for path in (run_path, output_csv, mapping_path)]
    if len(set(paths)) != 3:
        raise ValueError("Run, blinded CSV and private mapping must have different paths")
    if output_csv.exists() or mapping_path.exists():
        raise ValueError("Annotation outputs already exist; choose new paths to preserve human work")
    expected_conditions = _expected_conditions(expected_conditions)
    rows = load_run(run_path)
    if {row["condition"] for row in rows} - set(expected_conditions):
        raise ValueError("Run contains conditions outside the declared expected set; declare every condition being compared")
    answered = sorted((row for row in rows if row["status"] == "answered"), key=lambda r: (r["query_id"], r["condition"]))
    rng = random.Random(seed)
    rng.shuffle(answered)
    mapping: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "run_sha256": _run_digest(rows), "seed": seed, "expected_conditions": list(expected_conditions), "items": []}
    sheet = []
    for row in answered:
        annotation_id = f"a_{rng.getrandbits(128):032x}"
        sheet.append({**{field: "" for field in CSV_FIELDS}, "annotation_id": annotation_id, **_blinded_content(row)})
        mapping["items"].append({"annotation_id": annotation_id, "query_id": row["query_id"], "condition": row["condition"]})
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(sheet)
    with mapping_path.open("x", encoding="utf-8") as handle:
        json.dump(mapping, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return {"answered_responses_to_annotate": len(sheet), "run_records": len(rows), "run_sha256": mapping["run_sha256"], "expected_conditions": list(expected_conditions)}


def wilson_interval(successes: int, trials: int) -> list[float] | None:
    """Two-sided 95% Wilson interval; undefined with no observations."""
    if trials == 0:
        return None
    if not 0 <= successes <= trials:
        raise ValueError("Binomial counts must satisfy 0 <= successes <= trials")
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def _rate(successes: int, trials: int, *, complete: bool = True) -> dict[str, Any]:
    return {
        "numerator": successes if complete else None,
        "denominator": trials,
        "value": successes / trials if complete and trials else None,
        "wilson_95_ci": wilson_interval(successes, trials) if complete else None,
        "complete": complete,
    }


def _binary(value: str, field: str, annotation_id: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value not in ("0", "1"):
        raise ValueError(f"{annotation_id}: {field} must be 0, 1, or blank")
    return int(value)


def _count(value: str, field: str, annotation_id: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{annotation_id}: {field} must be a nonnegative integer or blank")
    return int(value)


def _load_labels(
    annotations_path: str | Path, expected: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    labels = {}
    with Path(annotations_path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Annotation CSV has missing or duplicate headers")
        if set(reader.fieldnames) != set(CSV_FIELDS):
            raise ValueError(f"Annotation CSV must contain exactly these fields: {', '.join(CSV_FIELDS)}")
        for csv_row in reader:
            if None in csv_row or any(value is None for value in csv_row.values()):
                raise ValueError("Annotation CSV contains a malformed row")
            annotation_id = csv_row["annotation_id"].strip()
            if annotation_id not in expected:
                raise ValueError(f"Unknown annotation ID: {annotation_id!r}")
            if annotation_id in labels:
                raise ValueError(f"Duplicate annotation ID: {annotation_id}")
            original = _blinded_content(expected[annotation_id])
            if any(csv_row[field] != original[field] for field in ("question", "answer", "evidence")):
                raise ValueError(f"{annotation_id}: question, answer or evidence changed after export")
            parsed = {field: _binary(csv_row[field], field, annotation_id) for field in (*ERROR_FIELDS, "correct")}
            for field in ("supported_claims", "total_claims"):
                parsed[field] = _count(csv_row[field], field, annotation_id)
            supported, total = parsed["supported_claims"], parsed["total_claims"]
            if (supported is None) != (total is None):
                raise ValueError(f"{annotation_id}: supply both faithfulness counts or leave both blank")
            if total is not None and supported > total:
                raise ValueError(f"{annotation_id}: supported_claims exceeds total_claims")
            annotator = csv_row["annotator_id"].strip()
            if any(value is not None for value in parsed.values()) and not annotator:
                raise ValueError(f"{annotation_id}: entered labels require a human annotator_id")
            labels[annotation_id] = {**parsed, "annotator_id": annotator, "comments": csv_row["comments"]}
    return labels


def _condition_report(
    rows: list[dict[str, Any]], eligible_count: int, labels_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(row["status"] for row in rows)
    answered = [row for row in rows if row["status"] == "answered"]
    ratings = [labels_by_key.get((row["query_id"], row["condition"]), {}) for row in answered]
    error_complete = [label for label in ratings if all(label.get(field) is not None for field in ERROR_FIELDS)]
    errors = sum(any(label[field] == 1 for field in ERROR_FIELDS) for label in error_complete)
    correctness = [label["correct"] for label in ratings if label.get("correct") is not None]
    faithful = [label for label in ratings if label.get("total_claims") is not None]
    supported_claims = sum(label["supported_claims"] for label in faithful)
    total_claims = sum(label["total_claims"] for label in faithful)
    missing = eligible_count - len(rows)
    observed_complete = missing == 0
    annotation_complete = len(error_complete) == len(answered) and len(correctness) == len(answered)
    categories = {}
    for field in ERROR_FIELDS:
        observed = [label[field] for label in ratings if label.get(field) is not None]
        categories[field] = {
            "among_all_answered": _rate(sum(observed), len(answered), complete=len(observed) == len(answered)),
            "labeled_subset_only": _rate(sum(observed), len(observed)),
        }
    return {
        "eligible_queries": eligible_count,
        "observed_records": len(rows),
        "missing_records": missing,
        "answered": statuses["answered"],
        "abstained": statuses["abstained"],
        "infrastructure_errors": statuses["error"],
        "coverage": _rate(statuses["answered"], eligible_count, complete=observed_complete),
        "infrastructure_failure_rate": _rate(statuses["error"], eligible_count, complete=observed_complete),
        "annotations_complete": annotation_complete,
        "risk_annotations_complete": len(error_complete) == len(answered),
        "answered_with_complete_error_labels": len(error_complete),
        "answered_missing_error_labels": len(answered) - len(error_complete),
        "hallucination_risk_among_answered": _rate(errors, len(answered), complete=len(error_complete) == len(answered)),
        "risk_on_labeled_subset_only": _rate(errors, len(error_complete)),
        "error_categories_overlap": True,
        "error_categories": categories,
        "correctness_among_answered": _rate(sum(correctness), len(answered), complete=len(correctness) == len(answered)),
        "correctness_on_labeled_subset_only": _rate(sum(correctness), len(correctness)),
        "faithfulness": {
            "definition": "human-supported factual claims / human-counted factual claims; not 1 - hallucination risk",
            "optional_annotations_complete": len(faithful) == len(answered),
            "answered_with_claim_counts": len(faithful),
            "supported_claims_on_labeled_subset": supported_claims,
            "total_claims_on_labeled_subset": total_claims,
            "micro_average_on_labeled_subset": supported_claims / total_claims if total_claims else None,
            "micro_average_all_answered": supported_claims / total_claims if total_claims and len(faithful) == len(answered) else None,
            "responses_with_zero_claims": sum(label["total_claims"] == 0 for label in faithful),
        },
        "abstention_reasons": dict(Counter(str(row.get("reason") or "unspecified") for row in rows if row["status"] == "abstained")),
        "infrastructure_error_reasons": dict(Counter(str(row.get("reason") or "unspecified") for row in rows if row["status"] == "error")),
    }


def build_report(
    run_path: str | Path, mapping_path: str | Path, annotations_path: str | Path,
) -> dict[str, Any]:
    """Aggregate one adjudicated record per answered response; blanks stay unknown."""
    rows = load_run(run_path)
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8-sig"))
    if not isinstance(mapping, dict) or mapping.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported annotation mapping schema")
    if mapping.get("run_sha256") != _run_digest(rows):
        raise ValueError("Run digest differs from the frozen annotation export")
    expected_conditions = _expected_conditions(mapping.get("expected_conditions"))
    if {row["condition"] for row in rows} - set(expected_conditions):
        raise ValueError("Run contains conditions outside the mapping's declared expected set")
    by_key = {(row["query_id"], row["condition"]): row for row in rows if row["status"] == "answered"}
    expected: dict[str, dict[str, Any]] = {}
    seen_keys = set()
    items = mapping.get("items")
    if not isinstance(items, list):
        raise ValueError("Mapping items must be a list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid mapping item")
        annotation_id = item.get("annotation_id")
        if not isinstance(annotation_id, str) or not annotation_id:
            raise ValueError("Invalid mapping annotation_id")
        if not all(isinstance(item.get(field), str) for field in ("query_id", "condition")):
            raise ValueError("Invalid mapping query_id or condition")
        key = (item.get("query_id"), item.get("condition"))
        if annotation_id in expected or key in seen_keys or key not in by_key:
            raise ValueError("Duplicate or unknown item in private annotation mapping")
        expected[annotation_id] = by_key[key]
        seen_keys.add(key)
    if seen_keys != set(by_key):
        raise ValueError("Mapping does not cover every answered response")
    labels = _load_labels(annotations_path, expected)
    labels_by_key = {(expected[annotation_id]["query_id"], expected[annotation_id]["condition"]): value for annotation_id, value in labels.items()}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["split"]].append(row)
    splits = {}
    for split, split_rows in sorted(groups.items()):
        eligible = len({row["query_id"] for row in split_rows})
        splits[split] = {condition: _condition_report([row for row in split_rows if row["condition"] == condition], eligible, labels_by_key) for condition in expected_conditions}
    reports = [report for split in splits.values() for report in split.values()]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_sha256": mapping["run_sha256"],
        "expected_conditions": list(expected_conditions),
        "matched_run_complete": all(report["missing_records"] == 0 for report in reports),
        "annotations_complete": all(report["annotations_complete"] for report in reports),
        "complete_for_primary_descriptive_reporting": all(report["missing_records"] == 0 and report["risk_annotations_complete"] for report in reports),
        "blinded_responses_expected": len(expected),
        "annotation_rows_present": len(labels),
        "missing_annotation_ids": sorted(set(expected) - set(labels)),
        "definitions": {
            "eligible": "All distinct query IDs within each split in the frozen run; every declared expected condition is required. Entirely absent queries require an external dataset-manifest check.",
            "coverage": "answered / all eligible queries; infrastructure failures remain in the denominator and are reported separately",
            "hallucination_risk": "answered responses with any of the three human error labels / answered responses; undefined if required labels are missing",
            "infrastructure_errors": "Not abstentions, correct answers, or clinically safe responses; excluded from clinical answer-risk denominators because no evaluable answer exists",
            "intervals": "Descriptive two-sided 95% Wilson intervals per condition; no paired significance claim, multiplicity adjustment, or clinical safety certification",
            "human_review": "CSV values are supplied by humans; this tool cannot certify reviewer expertise, independence, source validation, or adjudication",
        },
        "splits": splits,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Export blank blinded annotations and private mapping")
    export.add_argument("--input", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--mapping", required=True, type=Path)
    export.add_argument("--seed", type=int, default=2026)
    export.add_argument("--expected-conditions", default=",".join(CORE_CONDITIONS), help="Prespecified comparison conditions; default V,V_L,V_G. Include V_GL explicitly for four conditions.")
    report = commands.add_parser("report", help="Aggregate human annotations; incomplete metrics remain undefined")
    report.add_argument("--input", required=True, type=Path)
    report.add_argument("--mapping", required=True, type=Path)
    report.add_argument("--annotations", required=True, type=Path)
    report.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export_annotations(args.input, args.output, args.mapping, seed=args.seed, expected_conditions=[item.strip() for item in args.expected_conditions.split(",")])
        else:
            if args.output.resolve() in {path.resolve() for path in (args.input, args.mapping, args.annotations)}:
                raise ValueError("Report output cannot overwrite an input")
            result = build_report(args.input, args.mapping, args.annotations)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
