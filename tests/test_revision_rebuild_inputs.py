import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from backend.evaluation.revision.prepare_rebuild_inputs import prepare, split_ingestion_runs


def chunk(source, index, total, text):
    return {"source": source, "chunk_index": index, "total_chunks": total, "text": text}


class RebuildInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metadata = {
            0: chunk("a.pdf", 0, 2, "one two"),
            1: chunk("a.pdf", 1, 2, "three four"),
            # A different complete chunking of the same text.
            2: chunk("a.pdf", 0, 1, "one two three four"),
            3: chunk("alias.pdf", 0, 1, "one two three four"),
            # A failed upload must not become a complete document.
            4: chunk("partial.pdf", 0, 3, "incomplete text"),
        }
        self.summary = {
            "results": [
                {"success": True, "filename": "a.pdf", "chunks": 1, "total_vectors": 3,
                 "entities": 4, "nodes": 3, "relationships": 2},
                {"success": True, "filename": "alias.pdf", "chunks": 1, "total_vectors": 4,
                 "entities": 4, "nodes": 3, "relationships": 2},
                {"success": False, "filename": "partial.pdf"},
            ],
            "successful_uploads": 2, "total_chunks_ingested": 2,
            "upload_date": "fixture", "source_directory": "fixture",
            "initial_stats": {}, "final_stats": {},
        }

    def run_prepare(self):
        metadata = self.root / "metadata.npy"
        summary = self.root / "summary.json"
        np.save(metadata, self.metadata)
        summary.write_text(json.dumps(self.summary), encoding="utf-8")
        return prepare(metadata, summary, self.root / "output")

    def test_terminal_vector_matching_aliases_and_incomplete_exclusion(self):
        audit = self.run_prepare()
        selected = [json.loads(line) for line in (self.root / "output/selected_documents.jsonl").read_text().splitlines()]
        self.assertEqual(selected[0]["original_faiss_rows"], [2])
        self.assertEqual(audit["reconstructed_documents"], 2)
        self.assertEqual(audit["distinct_reconstructed_texts"], 1)
        self.assertEqual(audit["reported_node_attempts_sum"], 6)
        full = [json.loads(line) for line in (self.root / "output/full_recovered_documents.jsonl").read_text().splitlines()]
        self.assertEqual([doc["source"] for doc in full], ["a.pdf", "alias.pdf"])
        self.assertEqual(len(full[0]["provenance"]["original_ingestion_runs"]), 2)
        self.assertEqual(full[0]["text"], "one two three four")
        self.assertEqual([run["source"] for run in audit["full_recovered_excluded_runs"]], ["partial.pdf"])
        self.assertFalse(audit["original_graph_identity_restored"])

    def test_missing_successful_chunk_fails_before_writing_outputs(self):
        self.summary["results"][0].update(chunks=2, total_vectors=2)
        self.summary["total_chunks_ingested"] = 3
        del self.metadata[0]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.run_prepare()
        self.assertFalse((self.root / "output").exists())

    def test_wrong_terminal_count_cannot_select_a_different_upload(self):
        self.summary["results"][0]["total_vectors"] = 10
        with self.assertRaisesRegex(ValueError, "uniquely match"):
            self.run_prepare()

    def test_row_gaps_and_index_resets_are_distinct_runs(self):
        runs = split_ingestion_runs({
            0: chunk("a.pdf", 0, 2, "a"),
            2: chunk("a.pdf", 1, 2, "b"),
            3: chunk("a.pdf", 0, 2, "c"),
            4: chunk("a.pdf", 1, 2, "d"),
        })
        self.assertEqual([[row for row, _ in run] for run in runs], [[0], [2], [3, 4]])


if __name__ == "__main__":
    unittest.main()
