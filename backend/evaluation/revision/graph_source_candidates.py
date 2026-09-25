"""Find lexical source candidates for human review; never certify graph provenance.

Endpoint co-occurrence is a search heuristic, not relation entailment. This tool
does not add sources to the graph, reconstruct historical citations, or label
clinical facts. Exact original excerpts and offsets remain available for review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from .graph_verifier import FrozenGraph


def endpoint_names(node):
    props = node.get("properties", {})
    values = [props.get("name", ""), *props.get("aliases", [])]
    return sorted({v.strip() for v in values if isinstance(v, str) and v.strip()})


def literal_pattern(name):
    # Only case/whitespace variation; no stemming, clinical synonyms or aliases inferred.
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, name.split())) + r"(?!\w)", re.IGNORECASE)


def closest_pair(left, right):
    best = None
    for a in left:
        for b in right:
            start, end = min(a[0], b[0]), max(a[1], b[1])
            item = (end - start, start, end, a[2], b[2])
            if best is None or item < best:
                best = item
    return best


def find_candidates(snapshot, corpus, *, top_k=3, max_span=600, context_chars=140):
    if top_k < 1 or max_span < 1 or context_chars < 0:
        raise ValueError("Invalid candidate-search limits")
    FrozenGraph(snapshot)
    if len({item["doc_id"] for item in corpus}) != len(corpus):
        raise ValueError("Corpus doc IDs must be unique")
    for item in corpus:
        if hashlib.sha256(item["text"].encode()).hexdigest() != item["text_sha256"]:
            raise ValueError("Corpus text checksum mismatch")
    nodes = {node["id"]: node for node in snapshot["nodes"]}
    patterns = {key: [(name, literal_pattern(name)) for name in endpoint_names(node)] for key, node in nodes.items()}
    matches = {}
    for key, variants in patterns.items():
        matches[key] = {}
        for i, item in enumerate(corpus):
            hits = [(m.start(), m.end(), name) for name, pattern in variants for m in pattern.finditer(item["text"])]
            if hits:
                matches[key][i] = hits
    results = []
    for edge_index, edge in enumerate(snapshot["edges"]):
        source, target = edge["source"], edge["target"]
        candidates = []
        for index in matches[source].keys() & matches[target].keys():
            span, start, end, source_term, target_term = closest_pair(matches[source][index], matches[target][index])
            if span > max_span:
                continue
            item = corpus[index]
            left, right = max(0, start - context_chars), min(len(item["text"]), end + context_chars)
            candidates.append({"doc_id": item["doc_id"], "source": item.get("source"),
                               "source_id": item.get("source_id"), "chunk_index": item.get("chunk_index"),
                               "text_sha256": item["text_sha256"], "endpoint_span_chars": span,
                               "source_term": source_term, "target_term": target_term,
                               "excerpt_start": left, "excerpt_end": right, "excerpt": item["text"][left:right]})
        candidates.sort(key=lambda c: (c["endpoint_span_chars"], c["doc_id"]))
        # Prefer different source documents instead of near-duplicate chunks.
        selected, seen_sources = [], set()
        for candidate in candidates:
            identity = candidate["source_id"] or candidate["source"] or candidate["doc_id"]
            if identity not in seen_sources:
                selected.append(candidate)
                seen_sources.add(identity)
            if len(selected) == top_k:
                break
        results.append({"edge_index": edge_index, "edge_id": edge.get("id"), "relation": edge["type"],
                        "source_names": endpoint_names(nodes[source]), "target_names": endpoint_names(nodes[target]),
                        "search_status": "candidates_found" if selected else "no_lexical_candidate",
                        "matching_corpus_items": len(candidates), "candidates": selected,
                        "historical_source_recovered": None, "source_entailment": None,
                        "clinical_validation": None})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-span", type=int, default=600)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory exists; choose a new one to preserve review work")
    snapshot = json.loads(args.graph.read_text(encoding="utf-8"))
    corpus = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = find_candidates(snapshot, corpus, top_k=args.top_k, max_span=args.max_span)
    fields = ["edge_index", "edge_id", "source_names", "relation", "target_names", "search_status", "candidate_rank",
              "source", "chunk_index", "doc_id", "text_sha256", "excerpt_start", "excerpt_end", "excerpt",
              "annotator_id", "source_entails_relation", "direction_correct", "final_source_citation", "comments"]
    args.output_dir.mkdir(parents=True)
    with (args.output_dir / "source_candidates_for_review.csv").open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for edge in results:
            for rank, candidate in enumerate(edge["candidates"] or [{}], start=1):
                row = {key: "" for key in fields}
                row.update({key: edge[key] for key in ("edge_index", "edge_id", "relation", "search_status")})
                row.update({key: " | ".join(edge[key]) for key in ("source_names", "target_names")})
                row.update({key: value for key, value in candidate.items() if key in fields})
                row["candidate_rank"] = rank if candidate else ""
                writer.writerow(row)
    manifest = {"schema_version": 1, "purpose": "human source search queue; co-occurrence is not entailment or recovered provenance",
                "graph_sha256": hashlib.sha256(args.graph.read_bytes()).hexdigest(),
                "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "top_k_different_sources": args.top_k, "max_endpoint_span_chars": args.max_span,
                "corpus_items": len(corpus), "edges": len(results),
                "search_counts": dict(Counter(r["search_status"] for r in results)),
                "candidate_rows": sum(len(r["candidates"]) for r in results),
                "human_labels": "all blank", "graph_modified": False, "results": results}
    with (args.output_dir / "source_candidates.json").open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
