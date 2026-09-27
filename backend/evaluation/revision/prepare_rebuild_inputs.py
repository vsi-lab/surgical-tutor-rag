"""Recover February bulk-upload inputs from trusted saved FAISS chunk text.

No PDFs are re-ingested and no graph records are created. Loading the existing
local NumPy metadata uses pickle: never substitute an untrusted metadata file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def split_ingestion_runs(metadata: dict) -> list[list[tuple[int, dict]]]:
    """Keep chunking variants and partial attempts distinct in original row order."""
    groups: list[list[tuple[int, dict]]] = []
    for raw_row, record in sorted(metadata.items(), key=lambda item: int(item[0])):
        row = int(raw_row)
        if not isinstance(record.get("text"), str) or not record["text"]:
            raise ValueError(f"Missing saved chunk text at row {row}")
        chunk_index = record.get("chunk_index")
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool) or chunk_index < 0:
            raise ValueError(f"Invalid local chunk index at row {row}")
        if not groups:
            groups.append([])
        elif (
            row != groups[-1][-1][0] + 1
            or record["source"] != groups[-1][-1][1]["source"]
            or chunk_index != groups[-1][-1][1]["chunk_index"] + 1
            or record.get("total_chunks") != groups[-1][-1][1].get("total_chunks")
        ):
            groups.append([])
        groups[-1].append((row, record))
    return groups


def prepare(metadata_path: Path, summary_path: Path, output_dir: Path) -> dict:
    import numpy as np

    output_file = output_dir / "selected_documents.jsonl"
    full_output_file = output_dir / "full_recovered_documents.jsonl"
    audit_file = output_dir / "rebuild_input_audit.json"
    if output_file.exists() or full_output_file.exists() or audit_file.exists():
        raise ValueError("Rebuild inputs already exist; choose a new output directory")
    metadata = np.load(metadata_path, allow_pickle=True).item()
    if not isinstance(metadata, dict):
        raise ValueError("Trusted metadata must be a row-indexed object")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    runs = split_ingestion_runs(metadata)
    metadata_hash = sha256_bytes(metadata_path.read_bytes())
    documents = []
    for order, result in enumerate(summary["results"]):
        if not result["success"]:
            continue
        source, chunks = result["filename"], result["chunks"]
        candidates = [run for run in runs if run[0][1]["source"] == source and run[-1][0] + 1 == result["total_vectors"]]
        if len(candidates) != 1:
            raise ValueError(f"Cannot uniquely match original terminal vector count for {source}")
        run = candidates[0]
        if len(run) != chunks or [record["chunk_index"] for _, record in run] != list(range(chunks)):
            raise ValueError(f"Saved chunk sequence is incomplete for successful upload {source}")
        if any(record.get("total_chunks") != chunks for _, record in run):
            raise ValueError(f"Declared chunk total differs for {source}")
        text = " ".join(record["text"] for _, record in run)
        text_hash = sha256_bytes(text.encode("utf-8"))
        documents.append({
            "document_id": "saved-" + sha256_bytes((source + "\n" + text_hash).encode("utf-8")),
            "source": source,
            "title": run[0][1].get("title"),
            "original_bulk_order": order,
            "text": text,
            "text_sha256": text_hash,
            "word_count": len(text.split()),
            "character_count": len(text),
            "chunk_count": len(run),
            "declared_total_chunks": chunks,
            "complete_saved_chunk_sequence": True,
            "original_pdf_byte_reproduction": False,
            "reconstruction": "One ASCII space between original stored chunks, in preserved FAISS/local-index order; original PDF layout, page boundaries and pre-chunk whitespace are not recovered.",
            "metadata_path": str(metadata_path),
            "metadata_sha256": metadata_hash,
            "original_faiss_rows": [row for row, _ in run],
            "terminal_vector_count_from_upload_summary": result["total_vectors"],
            "chunks": [{"faiss_index": row, "faiss_row": row, "chunk_index": record["chunk_index"], "text": record["text"], "text_sha256": sha256_bytes(record["text"].encode("utf-8")), "character_count": len(record["text"])} for row, record in run],
            "provenance": {"metadata_path": str(metadata_path), "metadata_sha256": metadata_hash,
                           "selection": "successful February upload matched exactly by filename, chunk count and terminal vector count",
                           "original_bulk_order": order, "faiss_row_start": run[0][0], "faiss_row_end": run[-1][0],
                           "text_sha256": text_hash, "ambiguous": False,
                           "assembly": {"chunk_words": len(run[0][1]["text"].split()), "overlap_words": 0},
                           "normalized_saved_text_not_original_pdf_bytes": True},
            "original_upload_reported_entities": result["entities"],
            "original_upload_reported_node_attempts": result["nodes"],
            "original_upload_reported_relationship_attempts": result["relationships"],
        })
    if len(documents) != summary["successful_uploads"] or sum(doc["chunk_count"] for doc in documents) != summary["total_chunks_ingested"]:
        raise ValueError("Reconstructed document/chunk totals do not match the upload summary")
    same_text: dict[str, list[str]] = defaultdict(list)
    for doc in documents:
        same_text[doc["text_sha256"]].append(doc["source"])
    # Every declared-complete source/text is eligible for the wider recovered corpus.
    # Different chunkings remain in provenance rather than being concatenated twice.
    complete_runs: dict[tuple[str, str], list[list[tuple[int, dict]]]] = defaultdict(list)
    run_details = []
    for run in runs:
        text = " ".join(record["text"] for _, record in run)
        text_hash = sha256_bytes(text.encode("utf-8"))
        first = run[0][1]
        declared = first.get("total_chunks")
        complete = first["chunk_index"] == 0 and declared == len(run)
        detail = {"source": first["source"], "faiss_row_start": run[0][0], "faiss_row_end": run[-1][0],
                  "chunk_count": len(run), "first_chunk_index": first["chunk_index"],
                  "last_chunk_index": run[-1][1]["chunk_index"], "declared_total_chunks": declared,
                  "chunk_words": len(first["text"].split()),
                  "text_sha256": text_hash, "complete_declared_sequence": complete}
        run_details.append(detail)
        if complete:
            complete_runs[(first["source"], text_hash)].append(run)
    full_documents = []
    for (source, text_hash), source_runs in complete_runs.items():
        run = source_runs[0]
        matching_refs = [detail for detail in run_details if detail["source"] == source and detail["text_sha256"] == text_hash]
        for detail in matching_refs:
            detail["matches_complete_saved_document"] = True
        text = " ".join(record["text"] for _, record in run)
        full_documents.append({
            "document_id": "saved-" + sha256_bytes((source + "\n" + text_hash).encode("utf-8")),
            "source": source, "title": run[0][1].get("title"), "text": text, "text_sha256": text_hash,
            "word_count": len(text.split()), "character_count": len(text), "chunk_count": len(run),
            "declared_total_chunks": run[0][1]["total_chunks"], "complete_saved_chunk_sequence": True,
            "original_pdf_byte_reproduction": False,
            "chunks": [{"chunk_index": record["chunk_index"], "faiss_index": row, "faiss_row": row,
                        "text": record["text"], "text_sha256": sha256_bytes(record["text"].encode("utf-8"))} for row, record in run],
            "provenance": {"metadata_path": str(metadata_path), "metadata_sha256": metadata_hash,
                           "selection": "all declared-complete saved documents; identical source/full-text aliases of runs collapsed",
                           "text_sha256": text_hash, "ambiguous": False,
                           "assembly": {"chunk_words": len(run[0][1]["text"].split()), "overlap_words": 0},
                           "canonical_chunking_row_start": run[0][0], "canonical_chunking_row_end": run[-1][0],
                           "original_ingestion_runs": matching_refs,
                           "normalized_saved_text_not_original_pdf_bytes": True,
                           "first_saved_occurrence": min(detail["faiss_row_start"] for detail in matching_refs)},
        })
    full_documents.sort(key=lambda doc: doc["provenance"]["first_saved_occurrence"])
    encoded = "".join(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n" for doc in documents).encode("utf-8")
    full_encoded = "".join(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n" for doc in full_documents).encode("utf-8")
    audit = {
        "schema_version": 1,
        "purpose": "saved-text inputs for a documented graph rebuild; not recovery of the original graph",
        "metadata_path": str(metadata_path),
        "metadata_sha256": metadata_hash,
        "metadata_rows": len(metadata),
        "metadata_source_names": len({record["source"] for record in metadata.values()}),
        "metadata_contiguous_ingestion_runs": len(runs),
        "upload_summary_path": str(summary_path),
        "upload_summary_sha256": sha256_bytes(summary_path.read_bytes()),
        "original_upload_date": summary["upload_date"],
        "original_pdf_directory_recorded": summary["source_directory"],
        "reconstructed_documents": len(documents),
        "reconstructed_chunks": sum(doc["chunk_count"] for doc in documents),
        "distinct_reconstructed_texts": len(same_text),
        "identical_text_source_aliases": [sources for sources in same_text.values() if len(sources) > 1],
        "excluded_failed_uploads": [record["filename"] for record in summary["results"] if not record["success"]],
        "reported_node_attempts_sum": sum(doc["original_upload_reported_node_attempts"] for doc in documents),
        "reported_relationship_attempts_sum": sum(doc["original_upload_reported_relationship_attempts"] for doc in documents),
        "counter_interpretation": "GraphEnhancedIngestor increments approximate counts from extracted entity-list lengths before/independently of Neo4j MERGE uniqueness. These totals are not measured final database cardinalities.",
        "original_initial_stats": summary["initial_stats"],
        "original_final_stats": summary["final_stats"],
        "preservation_policy": "Keep successful upload order and identical-text source aliases because they were separate original uploads. Exclude the failed textbook upload; do not silently merge source/local chunk collisions.",
        "complete_original_documents_claimed": False,
        "original_graph_identity_restored": False,
        "documents_file": output_file.name,
        "documents_sha256": sha256_bytes(encoded),
        "full_recovered_documents_file": full_output_file.name,
        "full_recovered_documents_sha256": sha256_bytes(full_encoded),
        "full_recovered_document_count": len(full_documents),
        "full_recovered_canonical_chunk_count": sum(doc["chunk_count"] for doc in full_documents),
        "full_recovered_distinct_text_count": len({doc["text_sha256"] for doc in full_documents}),
        "full_recovered_excluded_runs": [detail for detail in run_details if not detail.get("matches_complete_saved_document")],
        "all_original_ingestion_runs": run_details,
        "documents": [{key: doc[key] for key in ("source", "original_bulk_order", "text_sha256", "chunk_count", "declared_total_chunks", "word_count", "terminal_vector_count_from_upload_summary")} | {"faiss_row_start": doc["original_faiss_rows"][0], "faiss_row_end": doc["original_faiss_rows"][-1]} for doc in documents],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_file.open("xb") as handle:
        handle.write(encoded)
    with full_output_file.open("xb") as handle:
        handle.write(full_encoded)
    with audit_file.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("backend/faiss_index.index.meta.npy.backup"))
    parser.add_argument("--upload-summary", type=Path, default=Path("backend/evaluation/results/bulk_upload_summary.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.metadata, args.upload_summary, args.output_dir)
    print(json.dumps({key: result[key] for key in ("reconstructed_documents", "reconstructed_chunks", "distinct_reconstructed_texts", "identical_text_source_aliases", "reported_node_attempts_sum", "reported_relationship_attempts_sum", "documents_sha256", "full_recovered_document_count", "full_recovered_canonical_chunk_count", "full_recovered_distinct_text_count")}, indent=2))


if __name__ == "__main__":
    main()
