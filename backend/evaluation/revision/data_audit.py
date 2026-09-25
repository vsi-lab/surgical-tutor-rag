"""Prepare auditable corpus/legacy manifests without creating relevance judgments.

Run: python -m backend.evaluation.revision.data_audit --output-dir PATH
Only NumPy is needed to read the repository's existing pickled metadata. Never use
--metadata with an untrusted .npy file: loading Python objects can execute code.
The exported legacy qrels are diagnostic hints, not independently judged truth.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from numbers import Integral
from pathlib import Path
import sys

try:
    from ..metrics.retrieval_metrics import source_chunk_id
except ImportError:  # Support direct execution as well as python -m.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from metrics.retrieval_metrics import source_chunk_id


EVALUATION_DIR = Path(__file__).resolve().parents[1]


def file_sha256(path):
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_question(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Every legacy record requires a nonempty question")
    return " ".join(question.split())


def query_identifier(question):
    return "legacy-" + sha256(normalize_question(question).encode("utf-8")).hexdigest()


def _local_index(record):
    for field in ("chunk_index", "chunk_id"):
        if record.get(field) is not None:
            return record[field]
    return None


def build_corpus_manifest(metadata):
    """Deduplicate identical source/local/text evidence; preserve every FAISS row."""
    if not isinstance(metadata, dict) or not metadata:
        raise ValueError("Metadata must be a nonempty mapping of FAISS rows")
    by_id, by_pair, by_row = {}, defaultdict(set), {}
    row_pair_counts = Counter()
    for raw_row, record in metadata.items():
        if isinstance(raw_row, bool) or not isinstance(raw_row, Integral) or raw_row < 0:
            raise ValueError("Metadata row IDs must be nonnegative integers")
        row = int(raw_row)
        if not isinstance(record, dict):
            raise ValueError(f"Invalid metadata record at row {row}")
        source, local, text = record.get("source"), _local_index(record), record.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Missing evidence text at metadata row {row}")
        pair_id = source_chunk_id(source, local)
        doc_id = source_chunk_id(source, local, text)
        if doc_id not in by_id:
            by_id[doc_id] = {
                "doc_id": doc_id,
                "source_id": pair_id.split("#chunk:", 1)[0],
                "source": source.strip(),
                "chunk_index": str(int(local)) if str(local).isdigit() else str(local),
                "text": text,
                "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "faiss_indices": [],
            }
        by_id[doc_id]["faiss_indices"].append(row)
        by_pair[pair_id].add(doc_id)
        by_row[row] = doc_id
        row_pair_counts[pair_id] += 1
    corpus = sorted(by_id.values(), key=lambda record: record["doc_id"])
    for record in corpus:
        record["faiss_indices"].sort()
    lookup = {"by_id": by_id, "by_pair": dict(by_pair), "by_row": by_row}
    summary = {
        "faiss_rows": len(metadata),
        "unique_evidence_documents": len(corpus),
        "exact_duplicate_rows_removed": len(metadata) - len(corpus),
        "unique_sources": len({record["source_id"] for record in corpus}),
        "repeated_source_chunk_pairs": sum(count > 1 for count in row_pair_counts.values()),
        "ambiguous_source_chunk_pairs": sum(len(ids) > 1 for ids in by_pair.values()),
        "id_definition": "source + local chunk index + SHA256(exact UTF-8 evidence text)",
    }
    return corpus, lookup, summary


def resolve_legacy_qrel(pair, lookup):
    """Resolve an address, never infer clinical relevance or change missing labels.

    Stored rows are accepted only when BOTH source and local chunk match. If a
    stored address is stale, fall back only to a unique source/local/text identity.
    Multiple identical rows are one evidence item; differing texts stay ambiguous.
    """
    warnings = []
    try:
        pair_id = source_chunk_id(pair.get("source"), pair.get("chunk_id"))
    except ValueError:
        return {"status": "missing_or_invalid_qrel", "doc_ids": [], "warnings": []}
    candidates = lookup["by_pair"].get(pair_id, set())
    stored_row = pair.get("faiss_index")
    if isinstance(stored_row, Integral) and not isinstance(stored_row, bool) and stored_row >= 0:
        row_id = lookup["by_row"].get(int(stored_row))
        if row_id in candidates:
            return {"status": "resolved_stored_row", "doc_ids": [row_id], "warnings": []}
        warnings.append("stored_row_missing_or_source_chunk_mismatch")
    elif stored_row is not None:
        warnings.append("invalid_stored_row")
    if len(candidates) == 1:
        return {"status": "resolved_unique_source_chunk", "doc_ids": sorted(candidates), "warnings": warnings}
    return {"status": "ambiguous_source_chunk" if candidates else "unmatched_source_chunk",
            "doc_ids": [], "warnings": warnings}


def build_legacy_query_manifest(datasets, lookup):
    """Merge questions across named datasets, retaining each original address audit."""
    merged = {}
    for dataset_name, pairs in datasets.items():
        if not isinstance(pairs, list):
            raise ValueError("Dataset qa_pairs must be a list")
        for position, pair in enumerate(pairs, 1):
            if not isinstance(pair, dict):
                raise ValueError("Every dataset item must be an object")
            question = normalize_question(pair.get("question"))
            query_id = query_identifier(question)
            resolution = resolve_legacy_qrel(pair, lookup)
            record = merged.setdefault(query_id, {
                "query_id": query_id,
                "question": question,
                "legacy_answer": pair.get("answer"),
                "category": pair.get("category"),
                "split": "legacy_diagnostic",
                "evidence_role": "legacy_diagnostic_only",
                "dataset_memberships": [],
                "legacy_records": [],
                "annotation_required": True,
                "independent_evaluation_eligible": False,
            })
            if dataset_name not in record["dataset_memberships"]:
                record["dataset_memberships"].append(dataset_name)
            record["legacy_records"].append({
                "dataset": dataset_name,
                "position": position,
                "source": pair.get("source"),
                "chunk_id": pair.get("chunk_id"),
                "faiss_index": pair.get("faiss_index"),
                "stored_retrieval_rank": pair.get("retrieval_rank"),
                "declared_validation_filtered": pair.get("validation_filtered"),
                "legacy_answer": pair.get("answer"),
                "qrel_resolution": resolution,
            })
    queries = []
    for record in merged.values():
        resolutions = [item["qrel_resolution"] for item in record["legacy_records"]]
        addresses = {tuple(item["doc_ids"]) for item in resolutions}
        if len(addresses) != 1:
            record["qrel_status"] = "conflicting_legacy_records"
            record["legacy_qrels"] = []
        else:
            record["legacy_qrels"] = list(next(iter(addresses)))
            statuses = {item["status"] for item in resolutions}
            record["qrel_status"] = next(iter(statuses)) if len(statuses) == 1 else (
                "resolved_mixed_provenance" if record["legacy_qrels"] else "unresolved_mixed_provenance")
        rank_stored = any(item["stored_retrieval_rank"] is not None for item in record["legacy_records"])
        record["selection_bias_status"] = "retrieval_rank_recorded_selection_affected" if rank_stored else "legacy_sampling_not_independently_validated"
        record["legacy_answer_conflict"] = len({json.dumps(item["legacy_answer"], sort_keys=True) for item in record["legacy_records"]}) > 1
        queries.append(record)
    return sorted(queries, key=lambda record: record["query_id"])


def annotation_candidates(queries):
    """A blank assessment queue, deliberately excluding legacy answers/qrel hints."""
    return [{
        "query_id": record["query_id"],
        "question": record["question"],
        "category": record["category"],
        "dataset_memberships": record["dataset_memberships"],
        "split": "legacy_diagnostic",
        "annotation_status": "awaiting_independent_assessment",
        "relevance_judgments": None,
        "answerability": None,
        "assessor_id": None,
        "adjudication": None,
        "independent_evaluation_eligible": False,
        "note": "Annotating legacy questions does not undo retrieval-based question selection. Author a separate unfiltered held-out set for confirmatory evaluation.",
    } for record in queries]


def audit_datasets(datasets, queries):
    memberships = {name: {query_identifier(pair.get("question")) for pair in pairs}
                   for name, pairs in datasets.items()}
    summary = {}
    for name, pairs in datasets.items():
        records = [item for query in queries for item in query["legacy_records"] if item["dataset"] == name]
        summary[name] = {
            "records": len(pairs), "unique_questions": len(memberships[name]),
            "duplicate_questions": len(pairs) - len(memberships[name]),
            "stored_retrieval_ranks": sum(pair.get("retrieval_rank") is not None for pair in pairs),
            "legacy_resolvable_records": sum(bool(item["qrel_resolution"]["doc_ids"]) for item in records),
            "qrel_status_counts": dict(sorted(Counter(item["qrel_resolution"]["status"] for item in records).items())),
        }
    names = list(datasets)
    overlap = [{"datasets": [left, right], "shared_questions": len(memberships[left] & memberships[right]),
                "query_ids": sorted(memberships[left] & memberships[right])}
               for i, left in enumerate(names) for right in names[i + 1:]]
    return {"datasets": summary, "overlap": overlap, "union_unique_questions": len(queries),
            "independently_judged_queries_created": 0,
            "all_legacy_queries_require_annotation": True}


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=EVALUATION_DIR.parent / "faiss_index.index.meta.npy")
    parser.add_argument("--primary-data", type=Path, default=EVALUATION_DIR / "test_data/expanded_test_set_60pairs.json")
    parser.add_argument("--comparison-data", type=Path, default=EVALUATION_DIR / "test_data/expanded_test_set_33pairs.json")
    parser.add_argument("--output-dir", type=Path, default=EVALUATION_DIR / "revision_outputs/data_audit")
    args = parser.parse_args(argv)
    import numpy as np  # The only nonstandard dependency; no model/API imports.
    metadata = np.load(args.metadata, allow_pickle=True).item()
    corpus, lookup, corpus_summary = build_corpus_manifest(metadata)
    datasets = {}
    paths = {"legacy60": args.primary_data, "legacy33": args.comparison_data}
    for name, path in paths.items():
        with path.open(encoding="utf-8") as handle:
            datasets[name] = json.load(handle)["qa_pairs"]
    queries = build_legacy_query_manifest(datasets, lookup)
    summary = {"schema_version": 1, "status": "legacy_audit_only_not_confirmatory_evidence",
               "corpus": corpus_summary, **audit_datasets(datasets, queries),
               "input_sha256": {"metadata": file_sha256(args.metadata),
                                **{name: file_sha256(path) for name, path in paths.items()}}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"corpus_manifest.jsonl": corpus, "legacy_queries.jsonl": queries,
               "annotation_candidates.jsonl": annotation_candidates(queries)}
    for filename, rows in outputs.items():
        _write_jsonl(args.output_dir / filename, rows)
    summary["output_sha256"] = {name: file_sha256(args.output_dir / name) for name in outputs}
    with (args.output_dir / "audit_summary.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    # Deliberately print counts only, never raw source result/config/environment data.
    print(json.dumps({"status": summary["status"], "corpus": corpus_summary,
                      "datasets": summary["datasets"], "union_unique_questions": len(queries),
                      "overlap_counts": [item["shared_questions"] for item in summary["overlap"]]}, indent=2))
    return summary


if __name__ == "__main__":
    main()
