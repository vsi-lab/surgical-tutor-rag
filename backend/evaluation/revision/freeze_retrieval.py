"""Freeze actual dense retrieval with sampled encoder/index alignment controls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .preflight import save_json


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def embed(texts, tokenizer, model, *, batch_size=8):
    import numpy as np
    import torch
    vectors = []
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            encoded = tokenizer(texts[start:start + batch_size], padding=True, truncation=True,
                                max_length=512, return_tensors="pt")
            hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1)
            values = ((hidden * mask).sum(1) / mask.sum(1).clamp(min=1)).cpu().numpy()
            vectors.append(values)
    result = np.concatenate(vectors).astype("float32")
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    if not np.isfinite(result).all() or (norms == 0).any():
        raise ValueError("Invalid embedding; cannot freeze retrieval")
    return result / norms


def freeze(args) -> dict:
    import faiss
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(args.cpu_threads)
    torch.manual_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    corpus = read_jsonl(args.corpus)
    queries = read_jsonl(args.queries)
    if args.limit:
        queries = queries[:args.limit]
    if not queries:
        raise ValueError("No queries")
    row_to_doc = {}
    for doc in corpus:
        for row in doc["faiss_indices"]:
            if int(row) in row_to_doc:
                raise ValueError("Duplicate FAISS row in corpus manifest")
            row_to_doc[int(row)] = doc
    index = faiss.read_index(str(args.index))
    if set(row_to_doc) != set(range(index.ntotal)):
        raise ValueError("Corpus manifest does not cover every FAISS row exactly once")
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=not args.allow_download)
    model = AutoModel.from_pretrained(args.model, local_files_only=not args.allow_download)
    model.eval()
    positions = np.linspace(0, index.ntotal - 1, min(11, index.ntotal), dtype=int).tolist()
    checks = embed([row_to_doc[i]["text"] for i in positions], tokenizer, model)
    distances, identifiers = index.search(checks, min(index.ntotal, 10))
    alignment = []
    for i, row in enumerate(positions):
        stored = index.reconstruct(row)
        self_score = float(np.dot(checks[i], stored) / max(float(np.linalg.norm(stored)), 1e-12))
        best_score = float(distances[i][0])
        aligned = self_score >= 0.99 and (row in identifiers[i] or self_score >= best_score - 1e-5)
        alignment.append({"faiss_row": row, "self_cosine": self_score,
                          "row_in_top10": row in identifiers[i], "aligned": bool(aligned)})
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "model": args.model,
                "model_commit": getattr(model.config, "_commit_hash", None),
                "pooling": "attention-mask mean pooling; max_length=512; L2 normalization",
                "index_sha256": sha256(args.index), "corpus_sha256": sha256(args.corpus),
                "queries_sha256": sha256(args.queries), "top_k_unique": args.top_k,
                "graph_reranking": False, "alignment_sample": alignment,
                "alignment_passed": all(x["aligned"] for x in alignment),
                "evaluation_role": "legacy diagnostic, not independent held-out performance"}
    save_json(args.output_dir / "retrieval_manifest.json", manifest)
    if not manifest["alignment_passed"]:
        raise ValueError("Encoder/index sample alignment failed; retrieval not run. See manifest.")
    vectors = embed([q["question"] for q in queries], tokenizer, model)
    scores, rows = index.search(vectors, index.ntotal)
    records, ranks = [], []
    for query, row_scores, row_ids in zip(queries, scores, rows):
        distinct, seen = [], set()
        for score, row in zip(row_scores, row_ids):
            doc = row_to_doc[int(row)]
            if doc["doc_id"] in seen:
                continue
            seen.add(doc["doc_id"])
            distinct.append({"chunk_id": "c-" + hashlib.sha256(doc["doc_id"].encode()).hexdigest()[:16],
                             "corpus_doc_id": doc["doc_id"], "source": doc["source"], "text": doc["text"],
                             "score": float(score), "faiss_row": int(row)})
        evidence = distinct[:args.top_k]
        records.append({"query_id": query["query_id"], "question": query["question"],
                        "split": query.get("split", "legacy_diagnostic"), "evidence": evidence,
                        "evidence_role": "legacy_diagnostic_only"})
        relevant = set(query.get("legacy_qrels", []))
        # Preserve unresolved labels as missing, never turn them into all-irrelevant truth.
        if relevant:
            rank = next((i + 1 for i, item in enumerate(distinct) if item["corpus_doc_id"] in relevant), None)
            ranks.append({"query_id": query["query_id"], "first_relevant_rank": rank,
                          "qrels": sorted(relevant), "qrel_status": query.get("qrel_status")})
    output = args.output_dir / "frozen_evidence.jsonl"
    output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    summary = {"query_count": len(queries), "resolvable_legacy_qrel_count": len(ranks),
               "unresolved_count": len(queries) - len(ranks), "corpus_unique_chunks": len(corpus),
               "corpus_faiss_rows": index.ntotal, "source_count": len({d["source"] for d in corpus}),
               "frozen_evidence_sha256": sha256(output), "per_query_legacy_ranks": ranks,
               "warning": "Selection-biased/incomplete legacy qrels. Diagnostic only; no new gold labels or clinical scores."}
    if ranks:
        summary["diagnostic_hit_at_5"] = sum(r["first_relevant_rank"] is not None and r["first_relevant_rank"] <= 5 for r in ranks) / len(ranks)
        summary["diagnostic_mrr"] = sum(1 / r["first_relevant_rank"] if r["first_relevant_rank"] else 0 for r in ranks) / len(ranks)
    save_json(args.output_dir / "retrieval_summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_query_legacy_ranks"}, indent=2))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--queries", type=Path, required=True)
    p.add_argument("--index", type=Path, default=Path("backend/faiss_index.index"))
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--model", default="emilyalsentzer/Bio_ClinicalBERT")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--cpu-threads", type=int, default=4)
    p.add_argument("--seed", type=int, default=311)
    p.add_argument("--allow-download", action="store_true")
    args = p.parse_args()
    if args.top_k < 1 or args.cpu_threads < 1 or args.limit < 0:
        p.error("top-k/cpu-threads must be positive; limit nonnegative")
    freeze(args)


if __name__ == "__main__":
    main()
