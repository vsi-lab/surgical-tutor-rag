"""Behavioral checks for deterministic, pre-generation graph verification."""

import unittest

from backend.evaluation.revision.graph_verifier import FrozenGraph, gate_chunks, verify_claims


def node(node_id, name=None, aliases=None, labels=None):
    properties = {}
    if name is not None:
        properties["name"] = name
    if aliases is not None:
        properties["aliases"] = aliases
    return {"id": node_id, "labels": labels or [], "properties": properties}


def edge(source, relation, target, **properties):
    return {"source": source, "target": target, "type": relation, "properties": properties}


def claim(source="a", relation="PRECEDES", target="b", chunk_id="chunk-1", **extra):
    return {
        "source": source, "relation": relation, "target": target,
        "chunk_id": chunk_id, "evidence_quote": "A occurs before B.", **extra,
    }


def graph(edges=(), nodes=None, **options):
    return FrozenGraph({
        "nodes": nodes if nodes is not None else [node("a", "Step A"), node("b", "Step B"), node("c", "Step C")],
        "edges": list(edges),
    }, **options)


class RevisionGraphVerifierTests(unittest.TestCase):
    def test_empty_and_all_unknown_cannot_certify_even_at_zero_thresholds(self):
        for expected in ([], [claim()]):
            with self.subTest(expected=expected):
                report = verify_claims(graph(), expected, min_support=0, min_coverage=0)
                self.assertIsNone(report["support_score"])
                self.assertEqual(report["coverage"], 0)
                self.assertFalse(report["eligible_to_answer"])
                self.assertFalse(report["contradiction_veto"])

    def test_missing_edge_is_unknown_and_default_requires_all_relations_known(self):
        report = verify_claims(graph([edge("a", "PRECEDES", "b")]), [claim(), claim("b", "PRECEDES", "c")])
        self.assertEqual(report["counts"], {"supported": 1, "contradicted": 0, "unknown": 1})
        self.assertEqual(report["support_score"], 1)
        self.assertEqual(report["coverage"], 0.5)
        self.assertFalse(report["eligible_to_answer"])
        self.assertEqual(report["reason"], "insufficient_graph_coverage")

    def test_claim_and_edge_provenance_survive_verification(self):
        fact = edge("a", "PRECEDES", "b", source_document="guideline.pdf", source_quote="Original passage")
        expected = claim()
        report = verify_claims(graph([fact]), [expected])
        decision = report["decisions"][0]
        self.assertEqual(decision["claim"], expected)
        self.assertEqual(decision["provenance"], [expected])
        self.assertEqual(decision["matched_edges"], [{"edge_index": 0, **fact}])
        self.assertTrue(report["eligible_to_answer"])
        self.assertEqual(report["coverage"], 1)

    def test_follows_equivalence_normalizes_graph_and_expected_claim(self):
        equivalent_edges = [edge("a", "PRECEDES", "b"), edge("b", "FOLLOWS", "a")]
        equivalent_claims = [claim(), claim("b", "FOLLOWS", "a")]
        for fact in equivalent_edges:
            for expected in equivalent_claims:
                with self.subTest(fact=fact, expected=expected):
                    report = verify_claims(graph([fact]), [expected])
                    self.assertTrue(report["eligible_to_answer"])
                    self.assertEqual(report["decisions"][0]["canonical_relation"], {"source": "a", "relation": "PRECEDES", "target": "b"})

    def test_reverse_order_is_explicit_contradiction(self):
        for fact in [edge("b", "PRECEDES", "a"), edge("a", "FOLLOWS", "b")]:
            with self.subTest(fact=fact):
                report = verify_claims(graph([fact]), [claim()])
                self.assertEqual(report["counts"]["contradicted"], 1)
                self.assertTrue(report["contradiction_veto"])
                self.assertFalse(report["eligible_to_answer"])

    def test_simultaneous_support_and_opposite_always_veto(self):
        frozen = graph([edge("a", "PRECEDES", "b"), edge("b", "PRECEDES", "a")])
        report = verify_claims(frozen, [claim(required=False)], min_support=0, min_coverage=0, hard_contradiction_veto=False)
        self.assertEqual(report["counts"], {"supported": 0, "contradicted": 1, "unknown": 0})
        self.assertEqual(report["conflict_count"], 1)
        self.assertTrue(report["contradiction_veto"])
        self.assertEqual(report["reason"], "graph_conflict")
        self.assertTrue(report["decisions"][0]["matched_edges"])
        self.assertTrue(report["decisions"][0]["opposing_edges"])

    def test_temporal_self_loop_is_conflict(self):
        report = verify_claims(graph([edge("a", "PRECEDES", "a")]), [claim(target="a")])
        self.assertEqual(report["reason"], "graph_conflict")
        self.assertFalse(report["eligible_to_answer"])

    def test_contraindication_needs_explicit_opposite_same_endpoints(self):
        expected = claim("a", "CONTRAINDICATES", "b")
        for facts, state in [([], "unknown"), ([edge("b", "ALLOWS", "a")], "unknown"), ([edge("a", "ALLOWS", "b")], "contradicted")]:
            with self.subTest(facts=facts):
                report = verify_claims(graph(facts), [expected])
                self.assertEqual(report["decisions"][0]["state"], state)
        converse = verify_claims(graph([edge("a", "CONTRAINDICATES", "b")]), [claim("a", "ALLOWS", "b")])
        self.assertEqual(converse["decisions"][0]["state"], "contradicted")

    def test_all_labels_can_participate_and_predicates_are_not_rewritten(self):
        nodes = [node("a", labels=["Condition"]), node("b", labels=["Procedure"])]
        frozen = graph([edge("a", "CONTRAINDICATED_WITH", "b")], nodes)
        exact = verify_claims(frozen, [claim("a", "CONTRAINDICATED_WITH", "b")])
        self.assertTrue(exact["eligible_to_answer"])
        for relation in ("CONTRAINDICATES", "contraindicated_with"):
            with self.subTest(relation=relation):
                self.assertEqual(verify_claims(frozen, [claim("a", relation, "b")])["counts"]["unknown"], 1)

    def test_exact_normalized_names_aliases_and_ambiguous_alias(self):
        nodes = [node("a", "Step A", ["Exposure", "Shared"]), node("b", "Step B", ["Shared"])]
        frozen = graph([edge("a", "PRECEDES", "b")], nodes)
        for source in ("a", "  STEP   A ", " exposure "):
            self.assertTrue(verify_claims(frozen, [claim(source, target="step b")])["eligible_to_answer"])
        ambiguous = verify_claims(frozen, [claim("shared")])["decisions"][0]
        self.assertEqual(ambiguous["reason"], "ambiguous_entity")
        self.assertEqual(ambiguous["resolution"]["source"]["candidates"], ["a", "b"])
        fuzzy = verify_claims(frozen, [claim("Step")])["decisions"][0]
        self.assertEqual(fuzzy["reason"], "unresolved_entity")

    def test_exact_id_takes_precedence_over_another_nodes_alias(self):
        nodes = [node("a", "A"), node("b", "B", ["a"])]
        report = verify_claims(graph([edge("a", "PRECEDES", "b")], nodes), [claim()])
        self.assertTrue(report["eligible_to_answer"])
        self.assertEqual(report["decisions"][0]["resolution"]["source"]["matched_by"], "id")

    def test_no_transitive_inference_from_two_step_path(self):
        report = verify_claims(graph([edge("a", "PRECEDES", "b"), edge("b", "PRECEDES", "c")]), [claim(target="c")])
        self.assertEqual(report["counts"]["unknown"], 1)

    def test_duplicates_do_not_inflate_coverage_and_preserve_origins(self):
        expected = [claim(required=False), claim("Step A"), claim("b", "FOLLOWS", "a"), claim("b", "PRECEDES", "c")]
        report = verify_claims(graph([edge("a", "PRECEDES", "b")]), expected)
        self.assertEqual(report["input_claim_count"], 4)
        self.assertEqual(report["expected_relation_count"], 2)
        self.assertEqual(report["coverage"], 0.5)
        self.assertEqual(len(report["decisions"][0]["provenance"]), 3)
        self.assertTrue(report["decisions"][0]["required"])

    def test_prespecified_soft_policy_and_optional_contradiction_are_explicit(self):
        frozen = graph([edge("a", "PRECEDES", "b"), edge("a", "ALLOWS", "b")])
        expected = [claim(), claim("a", "CONTRAINDICATES", "b")]
        self.assertFalse(verify_claims(frozen, expected, min_support=0.5)["eligible_to_answer"])
        soft = verify_claims(frozen, expected, min_support=0.5, hard_contradiction_veto=False)
        self.assertTrue(soft["eligible_to_answer"])
        self.assertEqual(soft["support_score"], 0.5)
        expected[1]["required"] = False
        self.assertTrue(verify_claims(frozen, expected, min_support=0.5)["eligible_to_answer"])

    def test_explicit_extra_opposite_relations_are_recorded(self):
        frozen = graph([edge("a", "FORBIDS", "b")], opposite_relations=[("REQUIRES", "FORBIDS")])
        report = verify_claims(frozen, [claim("a", "REQUIRES", "b")])
        self.assertTrue(report["contradiction_veto"])
        self.assertEqual(report["policy"]["opposite_relations"], [["FORBIDS", "REQUIRES"]])

    def test_missing_provenance_or_invalid_required_flag_does_not_certify(self):
        frozen = graph([edge("a", "PRECEDES", "b")])
        for change in ({"evidence_quote": ""}, {"chunk_id": ""}, {"required": "true"}, {"relation": " PRECEDES"}):
            with self.subTest(change=change):
                report = verify_claims(frozen, [claim(**change)])
                self.assertFalse(report["eligible_to_answer"])
                self.assertEqual(report["decisions"][0]["reason"], "invalid_claim")

    def test_gate_retains_only_passing_chunks_and_empty_p_is_rejected(self):
        chunks = [{"chunk_id": name, "text": name} for name in ("good", "reverse", "missing", "empty")]
        expected = {
            "good": [claim(chunk_id="good")],
            "reverse": [claim("b", "PRECEDES", "a", chunk_id="reverse")],
            "missing": [claim("b", "PRECEDES", "c", chunk_id="missing")],
        }
        report = gate_chunks(graph([edge("a", "PRECEDES", "b")]), chunks, expected)
        self.assertEqual(report["retained_chunks"], [chunks[0]])
        self.assertEqual(report["rejected_chunks"], chunks[1:])
        self.assertEqual(report["chunk_reports"]["empty"]["reason"], "empty_expected_relations")
        self.assertTrue(report["eligible_to_answer"])
        self.assertFalse(gate_chunks(graph(), chunks, expected)["eligible_to_answer"])

    def test_gate_rejects_duplicate_or_mismatched_chunk_identifiers(self):
        frozen, chunks = graph(), [{"chunk_id": "one", "text": "x"}]
        for candidates, expected in [(chunks * 2, {}), (chunks, {"two": []}), (chunks, {"one": [claim(chunk_id="two")]})]:
            with self.subTest(candidates=candidates, expected=expected):
                with self.assertRaises(ValueError):
                    gate_chunks(frozen, candidates, expected)

    def test_snapshot_rejects_dangling_edges_duplicate_ids_and_invalid_aliases(self):
        snapshots = [
            {"nodes": [node("a")], "edges": [edge("a", "PRECEDES", "b")]},
            {"nodes": [node("a"), node("a")], "edges": []},
            {"nodes": [node("a", aliases="string")], "edges": []},
        ]
        for snapshot in snapshots:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(ValueError):
                    FrozenGraph(snapshot)

    def test_snapshot_is_isolated_from_input_mutation(self):
        snapshot = {"nodes": [node("a"), node("b")], "edges": [edge("a", "PRECEDES", "b", provenance="source")]}
        frozen = FrozenGraph(snapshot)
        digest = frozen.checksum
        snapshot["edges"].clear()
        self.assertTrue(verify_claims(frozen, [claim()])["eligible_to_answer"])
        self.assertEqual(frozen.checksum, digest)
        report = verify_claims(frozen, [claim()])
        report["decisions"][0]["matched_edges"][0]["properties"]["provenance"] = "changed"
        self.assertEqual(verify_claims(frozen, [claim()])["decisions"][0]["matched_edges"][0]["properties"]["provenance"], "source")

    def test_invalid_thresholds_fail_before_evaluation(self):
        for value in (-0.1, 1.1, float("nan"), float("inf"), True):
            for option in ("min_support", "min_coverage"):
                with self.subTest(value=value, option=option):
                    with self.assertRaises(ValueError):
                        verify_claims(graph(), [], **{option: value})


if __name__ == "__main__":
    unittest.main()
