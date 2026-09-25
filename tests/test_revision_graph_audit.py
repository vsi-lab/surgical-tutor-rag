import csv
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from backend.evaluation.revision.graph_audit import GRAPH_LABEL_FIELDS, export_graph_sample


class GraphAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.graph = self.base / "graph.json"
        self.sheet = self.base / "triples.csv"
        self.manifest = self.base / "sample.json"
        self.snapshot = {
            "nodes": [{"id": "a", "properties": {"name": "Synthetic A"}}, {"id": "b", "properties": {"name": "Synthetic B"}}],
            "edges": [{"id": f"e{index}", "source": "a", "target": "b", "type": relation, "properties": {"source_document": "fixture", "source_quote": "Synthetic source text"}} for index, relation in enumerate(["RELATED"] * 6 + ["PRECEDES"] * 3 + ["CONTRAINDICATES"])],
        }
        self.write_graph()

    def write_graph(self):
        self.graph.write_text(json.dumps(self.snapshot), encoding="utf-8")

    def test_stratified_sample_preserves_rare_relations_and_blank_labels(self):
        result = export_graph_sample(self.graph, self.sheet, self.manifest, per_relation=2, seed=44)
        self.assertEqual(result["sample_size"], 5)
        self.assertEqual(result["strata"]["RELATED"], {"population": 6, "sample": 2})
        self.assertEqual(result["strata"]["CONTRAINDICATES"], {"population": 1, "sample": 1})
        self.assertIsNone(result["graph_quality_estimates"])
        self.assertFalse(result["submission_graph_identity_confirmed"])
        self.assertEqual(len({item["edge_index"] for item in result["items"]}), 5)
        with self.sheet.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(Counter(row["relation"] for row in rows), {"RELATED": 2, "PRECEDES": 2, "CONTRAINDICATES": 1})
        for row in rows:
            for field in (*GRAPH_LABEL_FIELDS, "annotator_id", "source_citation", "comments"):
                self.assertEqual(row[field], "")
            self.assertIn("Synthetic source text", row["edge_properties"])

    def test_seed_and_frozen_graph_determine_identical_sample(self):
        result = export_graph_sample(self.graph, self.sheet, self.manifest, per_relation=2, seed=44)
        second_sheet, second_manifest = self.base / "second.csv", self.base / "second.json"
        second = export_graph_sample(self.graph, second_sheet, second_manifest, per_relation=2, seed=44)
        self.assertEqual(result, second)
        self.assertEqual(self.sheet.read_bytes(), second_sheet.read_bytes())

    def test_existing_annotations_never_overwritten(self):
        export_graph_sample(self.graph, self.sheet, self.manifest)
        with self.assertRaisesRegex(ValueError, "already exist"):
            export_graph_sample(self.graph, self.sheet, self.manifest)

    def test_empty_or_invalid_graph_cannot_masquerade_as_validated(self):
        self.snapshot["edges"] = []
        self.write_graph()
        with self.assertRaisesRegex(ValueError, "no edges"):
            export_graph_sample(self.graph, self.sheet, self.manifest)
        self.snapshot["edges"] = [{"source": "missing", "target": "b", "type": "RELATED"}]
        self.write_graph()
        with self.assertRaisesRegex(ValueError, "unknown node"):
            export_graph_sample(self.graph, self.sheet, self.manifest)
        self.assertFalse(self.sheet.exists())

    def test_invalid_sample_size_and_overlapping_paths_rejected(self):
        for size in (0, -1, 1.5, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                export_graph_sample(self.graph, self.sheet, self.manifest, per_relation=size)
        with self.assertRaisesRegex(ValueError, "different paths"):
            export_graph_sample(self.graph, self.graph, self.manifest)


if __name__ == "__main__":
    unittest.main()
