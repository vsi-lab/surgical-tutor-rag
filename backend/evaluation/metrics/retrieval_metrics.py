"""Binary relevance metrics over unique, globally identified evidence.

Ranks are assigned after removing duplicate retrieved IDs, preserving first occurrence.
AP@k divides by *all* known relevant documents, not min(k, relevant count). MAP/MRR
without a cutoff use the entire supplied ranking; they cannot recover unreturned rows.
An empty qrel set means missing judgments here and is rejected, never scored as zero.
"""

from collections import defaultdict
from hashlib import sha256
from math import log2
from numbers import Integral
from statistics import fmean
from typing import Dict, List, Optional
from urllib.parse import quote


def source_chunk_id(source: str, chunk_index, text: Optional[str] = None) -> str:
    """Identify source/local-chunk evidence, optionally disambiguating its text.

    Corpus metadata can repeat a source/local index with different text. Pass text
    when constructing corpus IDs; exact duplicates then intentionally share one ID.
    Numeric zero is valid, unlike missing, negative or nonintegral chunk indices.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("A nonempty source identifier is required")
    if isinstance(chunk_index, bool) or chunk_index is None:
        raise ValueError("A nonnegative chunk index or nonempty chunk label is required")
    if isinstance(chunk_index, Integral):
        if chunk_index < 0:
            raise ValueError("Chunk index must be nonnegative")
        local_id = str(int(chunk_index))
    elif isinstance(chunk_index, str) and chunk_index.strip():
        local_id = chunk_index.strip()
        if local_id.lstrip("-").isdigit():
            if int(local_id) < 0:
                raise ValueError("Chunk index must be nonnegative")
            local_id = str(int(local_id))
    else:
        raise ValueError("Invalid chunk index")
    identifier = "source:" + quote(source.strip(), safe="") + "#chunk:" + quote(local_id, safe="")
    if text is not None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Chunk text must be nonempty when used to identify evidence")
        identifier += "#sha256:" + sha256(text.encode("utf-8")).hexdigest()
    return identifier


def _unique_ids(values, *, require_nonempty=False):
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("IDs must be a collection of nonempty strings")
    unique = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Every evidence ID must be a nonempty string")
        if value not in seen:
            seen.add(value)
            unique.append(value)
    if require_nonempty and not unique:
        raise ValueError("Missing relevance judgments: at least one qrel is required")
    return unique


def _cutoff(k):
    if isinstance(k, bool) or not isinstance(k, Integral) or k < 0:
        raise ValueError("k must be a nonnegative integer")
    return int(k)


def _prepare(retrieved_ids, relevant_ids, k=None):
    relevant = set(_unique_ids(relevant_ids, require_nonempty=True))
    retrieved = _unique_ids(retrieved_ids)
    if k is not None:
        retrieved = retrieved[:_cutoff(k)]
    return retrieved, relevant


class RetrievalMetrics:
    """Standard binary metrics; call sites must supply globally unique IDs."""

    @staticmethod
    def recall_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
        retrieved, relevant = _prepare(retrieved_ids, relevant_ids, k)
        return len(set(retrieved) & relevant) / len(relevant)

    @staticmethod
    def precision_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
        retrieved, relevant = _prepare(retrieved_ids, relevant_ids, k)
        return len(set(retrieved) & relevant) / k if k else 0.0

    @staticmethod
    def mean_reciprocal_rank(retrieved_ids: List[str], relevant_ids: List[str], k=None) -> float:
        retrieved, relevant = _prepare(retrieved_ids, relevant_ids, k)
        return next((1.0 / rank for rank, item in enumerate(retrieved, 1) if item in relevant), 0.0)

    @staticmethod
    def ndcg_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
        retrieved, relevant = _prepare(retrieved_ids, relevant_ids, k)
        dcg = sum(1.0 / log2(rank + 1) for rank, item in enumerate(retrieved, 1) if item in relevant)
        ideal = sum(1.0 / log2(rank + 1) for rank in range(1, min(len(relevant), k) + 1))
        return dcg / ideal if ideal else 0.0

    @staticmethod
    def average_precision(retrieved_ids: List[str], relevant_ids: List[str], k=None) -> float:
        """AP (or AP@k) normalized by the total unique relevant-document count."""
        retrieved, relevant = _prepare(retrieved_ids, relevant_ids, k)
        found, precision_sum = 0, 0.0
        for rank, item in enumerate(retrieved, 1):
            if item in relevant:
                found += 1
                precision_sum += found / rank
        return precision_sum / len(relevant)


def evaluate_retrieval(queries: List[Dict], retrieval_function,
                       k_values: Optional[List[int]] = None) -> Dict[str, float]:
    """Macro-average judged queries; validate every qrel before calling retrieval.

    Empty/unjudged queries must be excluded explicitly by the caller, with their
    exclusion counts reported. MRR/MAP retain their legacy names; explicit cutoff
    versions are also returned to prevent confusing top-k with full-ranking scores.
    """
    k_values = [1, 3, 5, 10] if k_values is None else list(dict.fromkeys(k_values))
    for k in k_values:
        _cutoff(k)
    if not queries:
        raise ValueError("At least one judged query is required")
    for query in queries:
        if not isinstance(query.get("query"), str) or not query["query"].strip():
            raise ValueError("Every query requires nonempty text")
        _unique_ids(query.get("relevant_doc_ids"), require_nonempty=True)
    results = defaultdict(list)
    metrics = RetrievalMetrics()
    for query in queries:
        relevant = query["relevant_doc_ids"]
        retrieved = _unique_ids(retrieval_function(query["query"]))
        for k in k_values:
            results[f"Recall@{k}"].append(metrics.recall_at_k(retrieved, relevant, k))
            results[f"Precision@{k}"].append(metrics.precision_at_k(retrieved, relevant, k))
            results[f"NDCG@{k}"].append(metrics.ndcg_at_k(retrieved, relevant, k))
            results[f"MRR@{k}"].append(metrics.mean_reciprocal_rank(retrieved, relevant, k))
            results[f"MAP@{k}"].append(metrics.average_precision(retrieved, relevant, k))
        results["MRR"].append(metrics.mean_reciprocal_rank(retrieved, relevant))
        results["MAP"].append(metrics.average_precision(retrieved, relevant))
    return {metric: fmean(scores) for metric, scores in results.items()}
