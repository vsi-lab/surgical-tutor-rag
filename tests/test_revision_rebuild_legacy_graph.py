import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.evaluation.revision import rebuild_legacy_graph as rebuild


def document(identifier="doc-a", source="a.pdf"):
    text = "Appendectomy involves appendix."
    return {"document_id": identifier, "source": source, "text": text,
            "chunks": [{"chunk_index": 0, "faiss_index": 1, "text": text}],
            "provenance": {"assembly": {"chunk_words": 400, "overlap_words": 0}}}


class FakeExtractor:
    def extract_entities(self, text):
        return {"procedures": ["appendectomy", "other procedure"], "anatomy": ["appendix"],
                "instruments": [], "complications": [], "techniques": [], "medications": []}

    def identify_main_procedures(self, text, top_n=3):
        if top_n != 5:
            raise ValueError("Original top-five procedure policy was changed")
        return [("appendectomy", 1)]

    def extract_procedure_specific_entities(self, text, procedure):
        return self.extract_entities(text)

    def extract_relationships(self, text):
        return [{"subject": "step A", "verb": "precedes", "object": "step B", "sentence": "A precedes B"}]


class LegacyGraphRebuildTests(unittest.TestCase):
    def test_explicit_overlap_roundtrip_and_whitespace_disclaimer(self):
        chunks = [{"chunk_index": 0, "text": "one two three"}, {"chunk_index": 1, "text": "three four five"}]
        self.assertEqual(rebuild.reconstruct_normalized_text(chunks, chunk_words=3, overlap_words=1), "one two three four five")
        selected = rebuild.validate_documents([document()])[0]
        self.assertFalse(selected["original_whitespace_recovered"])
        self.assertEqual(len(selected["text_sha256"]), 64)

    def test_conflicting_uploads_missing_chunks_and_wrong_overlap_fail(self):
        variants = [
            ([{"chunk_index": 0, "text": "a b"}, {"chunk_index": 0, "text": "a c"}], 2, 0),
            ([{"chunk_index": 0, "text": "a b"}, {"chunk_index": 2, "text": "c"}], 2, 0),
            ([{"chunk_index": 1, "text": "a b"}], 2, 0),
            ([{"chunk_index": 0, "text": "a b"}, {"chunk_index": 1, "text": "c d"}], 2, 1),
            ([{"chunk_index": 0, "text": "a"}, {"chunk_index": 1, "text": "b"}], 2, 0),
        ]
        for chunks, words, overlap in variants:
            with self.subTest(chunks=chunks), self.assertRaises(rebuild.ReconstructionError):
                rebuild.reconstruct_normalized_text(chunks, chunk_words=words, overlap_words=overlap)

    def test_documents_reject_undeclared_assembly_or_unmatched_text_and_hash(self):
        for changed in [{"text": "Different document"}, {"text_sha256": "wrong"}, {"provenance": {}},
                        {"provenance": {"assembly": {"chunk_words": 400, "overlap_words": 0}, "ambiguous": True}}]:
            with self.subTest(changed=changed), self.assertRaises(rebuild.ReconstructionError):
                rebuild.validate_documents([{**document(), **changed}])
        with self.assertRaises(rebuild.ReconstructionError):
            rebuild.validate_documents([document(), document()])

    def test_original_methods_keep_approximate_stats_separate_from_unique_counts(self):
        docs = [document(), document("doc-b", "alias.pdf")]
        original = copy.deepcopy(docs)
        snapshot, summary, reports, _ = rebuild.replay_documents(docs, FakeExtractor())
        self.assertEqual(docs, original)
        self.assertEqual(summary["documents_replayed"], 2)
        self.assertEqual(summary["unique_document_texts"], 1)
        self.assertEqual(summary["unique_nodes"], 2)
        self.assertEqual(summary["unique_edges"], 1)
        self.assertEqual(summary["legacy_approximate_totals"], {"entities_extracted": 6, "graph_nodes_created": 8, "graph_relationships_created": 6})
        self.assertEqual(summary["relation_type_counts"], {"INVOLVES": 1})
        self.assertTrue(summary["legacy_approximate_totals_are_not_unique_graph_counts"])
        self.assertFalse(summary["submission_graph_identity_confirmed"])
        self.assertEqual(snapshot["edges"][0]["properties"]["reconstruction_document_ids"], ["doc-a", "doc-b"])
        self.assertFalse(snapshot["edges"][0]["properties"]["human_validated"])
        self.assertEqual(reports[0]["extractor_trace"][-1]["returned_count"], 1)
        self.assertFalse(reports[0]["extractor_trace"][-1]["inserted_by_legacy_method"])
        self.assertNotIn("PRECEDES", summary["relation_type_counts"])

    def test_semantic_snapshot_is_deterministic_and_does_not_import_database_modules(self):
        docs = [document(), document("doc-b", "alias.pdf")]
        with patch.dict("sys.modules", {"neo4j": None, "dotenv": None}):
            first = rebuild.replay_documents(docs, FakeExtractor())
            second = rebuild.replay_documents(list(reversed(docs)), FakeExtractor())
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1]["semantic_graph_sha256"], second[1]["semantic_graph_sha256"])

    def test_legacy_swallowed_error_cannot_produce_a_successful_partial_snapshot(self):
        extractor = FakeExtractor()
        extractor.extract_relationships = Mock(side_effect=ValueError("synthetic late failure"))
        with self.assertRaises(rebuild.ReconstructionError):
            rebuild.replay_documents([document()], extractor)

    def test_cli_invalid_inputs_fail_before_model_load(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "documents.jsonl"
            path.write_text(json.dumps({**document(), "text": "wrong"}) + "\n", encoding="utf-8")
            with patch.object(rebuild, "load_extractor") as load:
                with self.assertRaises(rebuild.ReconstructionError):
                    rebuild.main(["--documents", str(path), "--model", "explicit-model", "--output-dir", str(root / "outputs")])
            load.assert_not_called()
            self.assertFalse((root / "outputs").exists())

    def test_exact_text_nlp_cache_preserves_case_and_is_cleared_between_documents(self):
        pipeline = Mock(side_effect=lambda text: object())
        cache = rebuild.DocumentNlpCache(pipeline)
        self.assertIs(cache("Exact"), cache("Exact"))
        self.assertIsNot(cache("Exact"), cache("exact"))
        self.assertEqual(pipeline.call_count, 2)

        class ParsingExtractor(FakeExtractor):
            def __init__(self):
                self.nlp = Mock(side_effect=lambda text: object())

            def extract_entities(self, text):
                self.nlp(text)
                self.nlp(text)
                return super().extract_entities(text)

        extractor = ParsingExtractor()
        original_pipeline = extractor.nlp
        events = []
        _, _, reports, _ = rebuild.replay_documents([document(), document("alias", "alias.pdf")], extractor, progress=events.append)
        self.assertIs(extractor.nlp, original_pipeline)
        self.assertEqual(original_pipeline.call_count, 2)
        self.assertEqual([event["event"] for event in events], ["document_started", "document_completed"] * 2)
        self.assertTrue(all(report["nlp_memoization"]["pipeline_calls"] == 1 for report in reports))
        self.assertTrue(all(report["nlp_memoization"]["exact_text_cache_hits"] >= 3 for report in reports))


if __name__ == "__main__":
    unittest.main()
