import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from backend.evaluation.revision.data_audit import (
    annotation_candidates, audit_datasets, build_corpus_manifest,
    build_legacy_query_manifest, main, query_identifier, resolve_legacy_qrel,
)


class RevisionDataAuditTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            0: {"source": "a.pdf", "chunk_index": 0, "text": "first evidence"},
            1: {"source": "b.pdf", "chunk_index": 0, "text": "other source"},
            2: {"source": "a.pdf", "chunk_index": 0, "text": "first evidence"},
            3: {"source": "a.pdf", "chunk_index": 0, "text": "different passage"},
            4: {"source": "a.pdf", "chunk_index": 1, "text": "unique passage"},
        }
        self.corpus, self.lookup, self.stats = build_corpus_manifest(self.metadata)

    def test_manifest_preserves_rows_but_deduplicates_only_exact_evidence(self):
        self.assertEqual(len(self.corpus), 4)
        self.assertEqual(self.lookup["by_row"][0], self.lookup["by_row"][2])
        self.assertNotEqual(self.lookup["by_row"][0], self.lookup["by_row"][3])
        self.assertEqual(self.stats["exact_duplicate_rows_removed"], 1)
        self.assertEqual(self.stats["ambiguous_source_chunk_pairs"], 1)
        self.assertEqual(sorted(i for row in self.corpus for i in row["faiss_indices"]), list(range(5)))

    def test_stored_row_must_match_both_source_and_local_chunk(self):
        resolved = resolve_legacy_qrel({"source": "a.pdf", "chunk_id": 0, "faiss_index": 0}, self.lookup)
        self.assertEqual(resolved["status"], "resolved_stored_row")
        wrong_source = resolve_legacy_qrel({"source": "a.pdf", "chunk_id": 0, "faiss_index": 1}, self.lookup)
        self.assertEqual(wrong_source["status"], "ambiguous_source_chunk")
        wrong_chunk = resolve_legacy_qrel({"source": "a.pdf", "chunk_id": 0, "faiss_index": 4}, self.lookup)
        self.assertEqual(wrong_chunk["doc_ids"], [])
        self.assertTrue(wrong_chunk["warnings"])

    def test_fallback_is_unique_and_missing_labels_stay_missing(self):
        resolved = resolve_legacy_qrel({"source": "a.pdf", "chunk_id": 1, "faiss_index": 999}, self.lookup)
        self.assertEqual(resolved["status"], "resolved_unique_source_chunk")
        self.assertTrue(resolved["warnings"])
        for pair in [{}, {"source": "a.pdf", "chunk_id": -1}, {"source": "a.pdf", "chunk_id": None}]:
            self.assertEqual(resolve_legacy_qrel(pair, self.lookup)["doc_ids"], [])

    def test_query_overlap_stable_ids_and_no_assigned_human_truth(self):
        q = {"question": "A question?", "answer": "legacy reference", "source": "a.pdf",
             "chunk_id": 1, "retrieval_rank": 1}
        datasets = {"legacy60": [q, {"question": "Unjudged?"}], "legacy33": [{**q, "question": " A  question? "}]}
        rows = build_legacy_query_manifest(datasets, self.lookup)
        self.assertEqual(len(rows), 2)
        self.assertEqual(query_identifier(" A  question? "), query_identifier("A question?"))
        summary = audit_datasets(datasets, rows)
        self.assertEqual(summary["overlap"][0]["shared_questions"], 1)
        self.assertEqual(summary["independently_judged_queries_created"], 0)
        for row in rows:
            self.assertFalse(row["independent_evaluation_eligible"])
            self.assertTrue(row["annotation_required"])
        for row in annotation_candidates(rows):
            self.assertIsNone(row["relevance_judgments"])
            self.assertIsNone(row["answerability"])
            self.assertNotIn("legacy_answer", row)
            self.assertNotIn("legacy_qrels", row)

    def test_conflicting_qrels_are_not_merged_into_false_multi_relevance(self):
        q = {"question": "same?", "source": "a.pdf", "chunk_id": 0}
        rows = build_legacy_query_manifest({"one": [{**q, "faiss_index": 0}],
                                            "two": [{**q, "faiss_index": 3}]}, self.lookup)
        self.assertEqual(rows[0]["qrel_status"], "conflicting_legacy_records")
        self.assertEqual(rows[0]["legacy_qrels"], [])

    def test_cli_writes_checksummed_manifests_and_no_raw_metadata_extras(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy required only for metadata file integration")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {key: {**value, "private_extra": "DO_NOT_EXPORT"} for key, value in self.metadata.items()}
            np.save(root / "meta.npy", metadata)
            primary = {"qa_pairs": [{"question": "question?", "source": "a.pdf", "chunk_id": 1}]}
            (root / "primary.json").write_text(json.dumps(primary), encoding="utf-8")
            (root / "compare.json").write_text(json.dumps({"qa_pairs": []}), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--metadata", str(root / "meta.npy"), "--primary-data", str(root / "primary.json"),
                               "--comparison-data", str(root / "compare.json"), "--output-dir", str(root / "output")])
            self.assertEqual(len(result["output_sha256"]), 3)
            self.assertEqual(result["union_unique_questions"], 1)
            all_output = stdout.getvalue() + "".join(path.read_text(encoding="utf-8") for path in (root / "output").iterdir())
            self.assertNotIn("DO_NOT_EXPORT", all_output)


if __name__ == "__main__":
    unittest.main()
