import hashlib
import unittest

from backend.evaluation.revision.graph_source_candidates import find_candidates


class SourceCandidateTests(unittest.TestCase):
    def graph(self):
        return {"nodes": [{"id": "a", "properties": {"name": "Alpha action"}},
                          {"id": "b", "properties": {"name": "Beta event"}}],
                "edges": [{"source": "a", "target": "b", "type": "MAY_CAUSE"}]}

    def doc(self, text, name="d1", source="s1"):
        return {"doc_id": name, "source_id": source, "source": source,
                "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}

    def test_negated_candidate_is_not_certified_and_offsets_preserved(self):
        text = "Context. ALPHA action does not cause Beta event. Review the actual relation."
        row = find_candidates(self.graph(), [self.doc(text)])[0]
        self.assertEqual(row["search_status"], "candidates_found")
        self.assertIsNone(row["source_entailment"])
        self.assertIsNone(row["historical_source_recovered"])
        candidate = row["candidates"][0]
        self.assertEqual(candidate["excerpt"], text[candidate["excerpt_start"]:candidate["excerpt_end"]])

    def test_boundaries_and_maximum_distance(self):
        for text in ("Alpha actions Beta events", "Alpha action " + "x" * 100 + " Beta event"):
            with self.subTest(text=text):
                row = find_candidates(self.graph(), [self.doc(text)], max_span=45)[0]
                self.assertEqual(row["search_status"], "no_lexical_candidate")

    def test_rank_prefers_nearby_mentions_and_diversifies_sources(self):
        docs = [self.doc("Alpha action " + "x" * 20 + " Beta event", "d1"),
                self.doc("Alpha action Beta event", "d2"),
                self.doc("Alpha action -> Beta event", "d3", "s2")]
        row = find_candidates(self.graph(), docs, top_k=3)[0]
        self.assertEqual([c["doc_id"] for c in row["candidates"]], ["d2", "d3"])
        self.assertEqual(row["matching_corpus_items"], 3)

    def test_unnamed_endpoint_remains_unmatched(self):
        graph = self.graph()
        graph["nodes"][0]["properties"] = {"image_path": "not a searchable entity"}
        row = find_candidates(graph, [self.doc("Alpha action Beta event")])[0]
        self.assertEqual(row["search_status"], "no_lexical_candidate")

    def test_hash_and_duplicate_identifiers_are_checked(self):
        doc = self.doc("Alpha action Beta event")
        with self.assertRaisesRegex(ValueError, "unique"):
            find_candidates(self.graph(), [doc, doc])
        doc["text"] += " changed"
        with self.assertRaisesRegex(ValueError, "checksum"):
            find_candidates(self.graph(), [doc])


if __name__ == "__main__":
    unittest.main()
