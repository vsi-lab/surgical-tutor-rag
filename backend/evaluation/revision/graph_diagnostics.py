"""Offline diagnostics of archived graph experiments; no model or human judgments.

python -m backend.evaluation.revision.graph_diagnostics --run-dir PATH
Reads a point-in-time snapshot, including a still-running log if its final line is
incomplete. It never repairs or reclassifies extraction failures as abstentions.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from decimal import Decimal
import difflib
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_log(path):
    raw = Path(path).read_bytes()
    lines = raw.splitlines()
    rows, incomplete = [], False
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            if index == len(lines) - 1 and not raw.endswith(b"\n"):
                incomplete = True
                continue
            raise ValueError(f"Malformed complete JSONL record in {Path(path).name} at line {index + 1}") from None
        if not isinstance(row, dict):
            raise ValueError("Archived log records must be objects")
        rows.append(row)
    return rows, {"sha256_at_read": hashlib.sha256(raw).hexdigest(),
                  "records_read": len(rows), "incomplete_final_line_skipped": incomplete}


def request_payload(call):
    for message in reversed(call.get("request", {}).get("messages", [])):
        if message.get("role") == "user":
            try:
                result = json.loads(message["content"])
                return result if isinstance(result, dict) else None
            except (ValueError, TypeError, KeyError):
                return None
    return None


def response_payload(row):
    return {"question": row["question"], "evidence": [
        {"chunk_id": chunk["chunk_id"], "source": chunk.get("source"), "text": chunk["text"]}
        for chunk in row.get("initial_evidence", [])]}


def quote_mismatch_kind(quote, evidence):
    """Diagnostic heuristics only: matching here never changes strict acceptance."""
    compact = lambda text: " ".join(text.split())
    if quote in evidence:
        return None
    if compact(quote) in compact(evidence):
        return "whitespace_or_linebreak_variation"
    if compact(quote).casefold() in compact(evidence).casefold():
        return "case_variation"
    q = compact(unicodedata.normalize("NFKC", quote).replace("\u00ad", ""))
    e = compact(unicodedata.normalize("NFKC", evidence).replace("\u00ad", ""))
    if q in e:
        return "unicode_normalization_variation"
    for replacement in ("", "-"):
        normalize_wrap = lambda text: re.sub(r"(?<=\w)-\s+(?=\w)", replacement, text)
        if normalize_wrap(q) in normalize_wrap(e):
            return "pdf_hyphenation_or_wrap_spacing"
    if "..." in quote or "…" in quote:
        return "ellipsis_or_discontinuous_quote"
    return "changed_or_unlocated_quote"


def quote_example(quote, evidence):
    block = difflib.SequenceMatcher(None, quote, evidence, autojunk=False).find_longest_match()
    start = max(0, block.b - block.a)
    return {"quoted_text_prefix": quote[:260], "nearby_evidence_prefix": evidence[start:start + 300],
            "classification": quote_mismatch_kind(quote, evidence),
            "classification_is_diagnostic_only": True}


def extraction_violations(call, relation_types):
    payload = request_payload(call)
    if call.get("status") != "ok":
        return [{"kind": "api_or_response_parse_failure"}]
    parsed = call.get("parsed")
    if not isinstance(parsed, dict) or not isinstance(parsed.get("claims"), list):
        return [{"kind": "invalid_claims_schema"}]
    chunks = {item.get("chunk_id"): item.get("text", "") for item in (payload or {}).get("evidence", [])}
    violations = []
    for index, claim in enumerate(parsed["claims"]):
        info = {"claim_index": index}
        if not isinstance(claim, dict):
            violations.append({**info, "kind": "malformed_claim"})
            continue
        info["chunk_id"] = claim.get("chunk_id")
        if claim.get("chunk_id") not in chunks:
            violations.append({**info, "kind": "invalid_chunk_id"})
            continue
        if any(not isinstance(claim.get(key), str) or not claim[key].strip()
               for key in ("source", "relation", "target", "evidence_quote")):
            violations.append({**info, "kind": "malformed_claim_fields"})
            continue
        if claim["relation"] not in relation_types:
            violations.append({**info, "kind": "undeclared_predicate", "predicate": claim["relation"]})
        text, quote = chunks[claim["chunk_id"]], claim["evidence_quote"]
        if quote not in text:
            violations.append({**info, "kind": "quote_mismatch", **quote_example(quote, text)})
    return violations


def unique_calls(calls):
    """Deduplicate copied provider responses, never distinct paid retries."""
    unique, conflicts = {}, []
    for call in calls:
        key = ("provider_response", call["response_id"]) if call.get("response_id") else (
            "unidentified_response", call.get("call_id"), call.get("request_sha256"), call.get("requested_at"))
        if key in unique and digest(unique[key]) != digest(call):
            conflicts.append({"call_id": call.get("call_id"), "response_id": call.get("response_id")})
        else:
            unique[key] = call
    return list(unique.values()), conflicts


def summarize(rows, calls, manifest, relation_types, *, max_examples=20):
    keys = [(row["query_id"], row["condition"]) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate query/condition response rows; resolve before aggregation")
    unique, cost_conflicts = unique_calls(calls)
    query_ids, conditions = set(manifest["query_ids"]), manifest["conditions"]
    expected = {(qid, arm) for qid in query_ids for arm in conditions}
    observed = set(keys)
    if observed - expected:
        raise ValueError("Response contains a query/condition absent from its run manifest")
    outcome_counts, errors_by_condition = {}, {}
    for arm in conditions:
        subset = [row for row in rows if row["condition"] == arm]
        counts = Counter(row["status"] for row in subset)
        outcome_counts[arm] = {"eligible": len(query_ids), "observed": len(subset),
                              "missing": len(query_ids) - len(subset),
                              **{state: counts[state] for state in ("answered", "abstained", "error")},
                              "coverage": counts["answered"] / len(query_ids) if query_ids and len(subset) == len(query_ids) else None}
        errors_by_condition[arm] = dict(Counter(row.get("reason", "unspecified") for row in subset if row["status"] == "error"))
    payload_queries = defaultdict(set)
    for row in rows:
        payload_queries[digest(response_payload(row))].add(row["query_id"])
    extraction_calls, violation_counts, mismatch_counts, predicate_counts = [], Counter(), Counter(), Counter()
    for call in unique:
        if call.get("purpose") != "relation_extraction":
            continue
        payload = request_payload(call)
        payload_hash = digest(payload) if payload is not None else None
        violations = extraction_violations(call, relation_types)
        violation_counts.update(item["kind"] for item in violations)
        mismatch_counts.update(item["classification"] for item in violations if item["kind"] == "quote_mismatch")
        predicate_counts.update(item["predicate"] for item in violations if item["kind"] == "undeclared_predicate")
        extraction_calls.append({"call_id": call.get("call_id"), "response_id": call.get("response_id"),
            "request_sha256": call.get("request_sha256"), "query_evidence_payload_sha256": payload_hash,
            "query_ids": sorted(payload_queries.get(payload_hash, [])), "api_status": call.get("status"),
            "claim_count": len(call["parsed"]["claims"]) if isinstance(call.get("parsed"), dict) and isinstance(call["parsed"].get("claims"), list) else None,
            "violation_counts": dict(Counter(item["kind"] for item in violations)),
            "violation_examples": violations[:max_examples]})
    # Shared V_G/V_GL reports count once per query and distinct trace fingerprint.
    traces = {}
    query_trace_keys = defaultdict(set)
    for row in rows:
        gate = row.get("graph_verification")
        if not isinstance(gate, dict):
            continue
        trace_hash = digest(gate.get("chunk_reports", {}))
        key = (row["query_id"], trace_hash)
        query_trace_keys[row["query_id"]].add(trace_hash)
        if key not in traces:
            traces[key] = {"query_id": row["query_id"], "trace_sha256": trace_hash, "conditions": [], "gate": gate}
        traces[key]["conditions"].append(row["condition"])
    chunk_reasons, relation_states, relation_reasons, entity_resolution, entity_mentions = (Counter() for _ in range(5))
    per_query = []
    for trace in traces.values():
        local_chunks, local_states, local_reasons = Counter(), Counter(), Counter()
        for report in trace["gate"].get("chunk_reports", {}).values():
            local_chunks[report.get("reason", "unspecified")] += 1
            for decision in report.get("decisions", []):
                local_states[decision.get("state", "unspecified")] += 1
                local_reasons[decision.get("reason", "unspecified")] += 1
                for endpoint, resolution in decision.get("resolution", {}).items():
                    status = resolution.get("status", "unspecified")
                    entity_resolution[f"{endpoint}:{status}"] += 1
                    if status != "resolved":
                        entity_mentions[str(decision.get("claim", {}).get(endpoint, ""))] += 1
        chunk_reasons.update(local_chunks); relation_states.update(local_states); relation_reasons.update(local_reasons)
        per_query.append({key: trace[key] for key in ("query_id", "trace_sha256", "conditions")} |
                         {"chunk_reasons": dict(local_chunks), "relation_states": dict(local_states),
                          "relation_reasons": dict(local_reasons), "retained_chunks": len(trace["gate"].get("retained_chunks", []))})
    known_cost = sum((Decimal(str(call["usage"]["cost"])) for call in unique if call.get("usage", {}).get("cost") is not None), Decimal(0))
    return {"schema_version": 1, "report_kind": "offline_execution_diagnostics_not_human_validation",
        "execution_records_complete": observed == expected,
        "all_requested_conditions_without_errors": observed == expected and all(row["status"] in ("answered", "abstained") for row in rows),
        "conditions": outcome_counts, "errors_by_condition": errors_by_condition,
        "graph_trace_queries": len(query_trace_keys), "unique_query_trace_pairs": len(traces),
        "shared_trace_double_counting_avoided": sum(bool(row.get("graph_verification")) for row in rows) - len(traces),
        "queries_with_differing_graph_traces": sorted(qid for qid, hashes in query_trace_keys.items() if len(hashes) > 1),
        "chunk_reasons": dict(chunk_reasons), "relation_states": dict(relation_states), "relation_reasons": dict(relation_reasons),
        "entity_endpoint_resolution": dict(entity_resolution), "unresolved_or_ambiguous_entity_mentions": dict(entity_mentions.most_common(max_examples)),
        "per_query_graph_traces": per_query,
        "extraction": {"unique_calls": len(extraction_calls), "calls_with_contract_violations": sum(bool(c["violation_counts"]) for c in extraction_calls),
                       "violation_counts": dict(violation_counts), "quote_mismatch_classifications": dict(mismatch_counts),
                       "undeclared_predicates": dict(predicate_counts), "calls": extraction_calls},
        "api_usage": {"input_log_records": len(calls), "unique_calls": len(unique), "copied_records_removed": len(calls) - len(unique),
                      "known_provider_cost_usd": str(known_cost), "calls_without_cost": sum(call.get("usage", {}).get("cost") is None for call in unique),
                      "duplicate_record_conflicts": cost_conflicts,
                      "api_statuses": dict(Counter(call.get("status", "unspecified") for call in unique)),
                      "calls_by_purpose": dict(Counter(call.get("purpose", "unspecified") for call in unique))},
        "human_quality_metrics": None,
        "limitations": ["API success and valid JSON do not establish extraction-contract compliance or clinical correctness.",
                        "Quote classifications are diagnostic heuristics, never repairs or accepted relevance judgments.",
                        "Relation and entity counts cover successfully checked graph traces; extraction failures have no graph decisions.",
                        "Missing execution rows are not abstentions. Required-relation coverage does not establish completeness.",
                        "Provider response IDs deduplicate copied calls; different response IDs remain separate paid calls."]}


def declared_relations(path):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "RELATION_TYPES" for target in node.targets):
            if isinstance(node.value, ast.Call) and node.value.args:
                return set(ast.literal_eval(node.value.args[0]))
    raise ValueError("No explicit RELATION_TYPES in archived runner")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--additional-call-log", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-examples", type=int, default=20)
    args = parser.parse_args(argv)
    if args.max_examples < 0:
        parser.error("max-examples must be nonnegative")
    manifest = json.loads((args.run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    rows, response_info = read_log(args.run_dir / "responses.jsonl")
    calls, input_logs = [], []
    for path in [args.run_dir / "model_calls.jsonl", *args.additional_call_log]:
        items, info = read_log(path)
        calls.extend(items)
        input_logs.append({"file": str(path), **info})
    snapshot = args.run_dir / "source_snapshot/run_matched.py"
    result = summarize(rows, calls, manifest, declared_relations(snapshot), max_examples=args.max_examples)
    result["inputs"] = {"responses": response_info, "call_logs": input_logs,
                        "relation_types_source": str(snapshot), "runner_snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()}
    output = args.output or args.run_dir / "graph_diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("execution_records_complete", "conditions", "errors_by_condition",
        "graph_trace_queries", "chunk_reasons", "relation_states", "relation_reasons", "api_usage")}, indent=2))
    return result


if __name__ == "__main__":
    main()
