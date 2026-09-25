import unittest
from math import log2

from backend.evaluation.metrics.retrieval_metrics import (
    RetrievalMetrics as Metrics, evaluate_retrieval, source_chunk_id,
)


class RevisionMetricsTests(unittest.TestCase):
    def test_duplicate_hits_cannot_inflate_ap_or_ndcg(self):
        ranking = ["a", "wrong", "a", "a"]
        self.assertEqual(Metrics.average_precision(ranking, ["a"]), 1.0)
        self.assertEqual(Metrics.ndcg_at_k(ranking, ["a"], 10), 1.0)

    def test_duplicates_are_removed_before_assigning_ranks_and_cutoffs(self):
        ranking = ["wrong", "wrong", "a"]
        self.assertEqual(Metrics.mean_reciprocal_rank(ranking, ["a"]), .5)
        self.assertEqual(Metrics.recall_at_k(ranking, ["a"], 2), 1.0)
        self.assertEqual(Metrics.precision_at_k(ranking, ["a"], 5), .2)

    def test_source_local_collisions_do_not_match(self):
        a = source_chunk_id("guideline-a.pdf", 0, "evidence")
        b = source_chunk_id("guideline-b.pdf", 0, "evidence")
        self.assertNotEqual(a, b)
        self.assertEqual(Metrics.average_precision([a], [b]), 0.0)

    def test_ids_disambiguate_local_collisions_and_delimiters(self):
        self.assertNotEqual(source_chunk_id("a#chunk:b", "c"), source_chunk_id("a", "b#chunk:c"))
        self.assertNotEqual(source_chunk_id("a", 0, "one"), source_chunk_id("a", 0, "two"))
        self.assertEqual(source_chunk_id("a", 0), source_chunk_id("a", "00"))
        for source, chunk in [(None, 0), ("", 0), ("a", None), ("a", -1), ("a", "-1"), ("a", False), ("a", 1.2)]:
            with self.subTest(source=source, chunk=chunk), self.assertRaises(ValueError):
                source_chunk_id(source, chunk)

    def test_single_qrel_ap_equals_reciprocal_rank_with_same_cutoff(self):
        ranking = ["x", "y", "a", "a"]
        for k in [0, 1, 2, 3, 10, None]:
            self.assertEqual(Metrics.average_precision(ranking, ["a"], k),
                             Metrics.mean_reciprocal_rank(ranking, ["a"], k))

    def test_ap_cutoff_uses_all_relevant_documents(self):
        ranking = ["a", "wrong", "b"]
        self.assertEqual(Metrics.average_precision(ranking, ["a", "b"], 1), .5)
        self.assertAlmostEqual(Metrics.average_precision(ranking, ["a", "b"]), (1 + 2 / 3) / 2)
        self.assertAlmostEqual(Metrics.ndcg_at_k(ranking, ["a", "b", "b"], 3),
                               (1 + 1 / log2(4)) / (1 + 1 / log2(3)))

    def test_empty_or_invalid_qrels_are_not_silently_negative(self):
        for qrels in [[], None, "a", [None], [" "]]:
            with self.subTest(qrels=qrels), self.assertRaises(ValueError):
                Metrics.average_precision(["a"], qrels)
        for k in [-1, 1.5, True]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                Metrics.recall_at_k(["a"], ["a"], k)

    def test_aggregate_prevalidates_and_names_cutoffs(self):
        calls = []
        def retrieve(query):
            calls.append(query)
            return ["x", "a", "a"]
        with self.assertRaises(ValueError):
            evaluate_retrieval([{"query": "one", "relevant_doc_ids": ["a"]},
                                {"query": "two", "relevant_doc_ids": []}], retrieve)
        self.assertEqual(calls, [])
        result = evaluate_retrieval([{"query": "one", "relevant_doc_ids": ["a"]}], retrieve, [1, 2])
        self.assertEqual(result["MAP"], .5)
        self.assertEqual(result["MRR"], .5)
        self.assertEqual(result["MAP@1"], 0)
        self.assertEqual(result["MAP@2"], .5)


if __name__ == "__main__":
    unittest.main()
