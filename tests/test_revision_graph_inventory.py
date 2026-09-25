"""Structural graph inventory tests using synthetic offline snapshots only."""

import json
from pathlib import Path
import tempfile
import unittest

from backend.evaluation.revision.graph_inventory import inventory_graph, render_markdown, write_inventory
from backend.evaluation.revision.graph_verifier import FrozenGraph


def node(identifier, name=None, **properties):
    return {"id": identifier, "labels": ["Entity"], "properties": {"name": name or identifier, **properties}}


def edge(subject, relation, target, **properties):
    return {"source": subject, "type": relation, "target": target, "properties": properties}


def snapshot(edges=(), nodes=None):
    return {"nodes": nodes if nodes is not None else [node("a"), node("b"), node("c")], "edges": list(edges)}


class GraphInventoryTests(unittest.TestCase):
    def test_actual_counts_labels_components_and_isolated_nodes(self):
        graph = snapshot([edge("a", "REQUIRES", "b")])
        report = inventory_graph(graph)
        self.assertEqual(report["node_count"], 3)
        self.assertEqual(report["edge_count"], 1)
        self.assertEqual(report["node_label_counts"], {"Entity": 3})
        self.assertEqual(report["relation_type_counts"], {"REQUIRES": 1})
        self.assertEqual(report["topology"]["weak_component_sizes"], [2, 1])
        self.assertEqual(report["topology"]["isolated_node_ids_sample"], ["c"])
        self.assertEqual(report["graph_sha256"], FrozenGraph(graph).checksum)
        self.assertIsNone(report["human_quality_metrics"])

    def test_duplicate_parallel_edges_distinguish_properties_and_canonical_form(self):
        edges = [edge("a", "PRECEDES", "b"), edge("a", "PRECEDES", "b"),
                 edge("a", "PRECEDES", "b", source="different"), edge("b", "FOLLOWS", "a")]
        report = inventory_graph(snapshot(edges))
        counts = report["duplicates"]
        self.assertEqual(counts["unique_exact_typed_triples"], 2)
        self.assertEqual(counts["parallel_exact_triple_extra_edges"], 2)
        self.assertEqual(counts["same_triple_and_properties_extra_edges"], 1)
        self.assertEqual(counts["canonical_triple_extra_edges"], 3)
        self.assertEqual(report["temporal_order"]["direct_reverse_conflict_count"], 0)

    def test_name_and_alias_ambiguities_use_verifier_normalization(self):
        graph = snapshot(nodes=[node("a", "Step   A", aliases=["shared"]), node("b", " step a ", aliases=["shared", "Other"]), node("c", "OTHER")])
        report = inventory_graph(graph)["entity_resolution"]
        self.assertEqual(report["ambiguous_normalized_name_count"], 1)
        self.assertEqual(report["ambiguous_name_or_alias_count"], 3)
        samples = {item["mention"]: item["node_ids"] for item in report["ambiguous_name_or_alias_samples"]}
        self.assertEqual(samples["step a"], ["a", "b"])
        self.assertEqual(samples["other"], ["b", "c"])

    def test_three_node_cycle_is_reported_without_inventing_direct_conflicts(self):
        report = inventory_graph(snapshot([edge("a", "PRECEDES", "b"), edge("b", "PRECEDES", "c"), edge("a", "FOLLOWS", "c")]))
        temporal = report["temporal_order"]
        self.assertEqual(temporal["cyclic_component_count"], 1)
        self.assertEqual(temporal["nodes_in_cyclic_components"], 3)
        self.assertEqual(temporal["direct_reverse_conflict_count"], 0)
        self.assertIn("temporal_cycles_present", report["flags"])

    def test_direct_reverse_conflicts_and_self_loops_count_once(self):
        report = inventory_graph(snapshot([edge("a", "PRECEDES", "b"), edge("b", "PRECEDES", "a"), edge("a", "FOLLOWS", "b"), edge("c", "PRECEDES", "c")]))
        temporal = report["temporal_order"]
        self.assertEqual(temporal["direct_reverse_conflict_count"], 2)
        self.assertEqual(temporal["cyclic_component_count"], 2)
        self.assertEqual(temporal["direct_reverse_conflicts_sample"], [["a", "b"], ["c", "c"]])

    def test_predicate_opposites_are_directional_and_legacy_names_are_distinct(self):
        graph = snapshot([edge("a", "CONTRAINDICATES", "b"), edge("a", "ALLOWS", "b"),
                          edge("b", "ALLOWS", "c"), edge("c", "CONTRAINDICATES", "b"),
                          edge("c", "CONTRAINDICATED_WITH", "a"), edge("c", "ALLOWS", "a")])
        report = inventory_graph(graph)
        self.assertEqual(report["explicit_opposites"]["same_endpoint_conflict_count"], 1)
        self.assertEqual(report["explicit_opposites"]["conflicts_sample"], [{"source": "a", "target": "b"}])

    def test_missing_key_predicates_are_flagged_without_equating_legacy_types(self):
        report = inventory_graph(snapshot([edge("a", "FOLLOWS", "b"), edge("a", "CONTRAINDICATED_WITH", "b")]))
        self.assertIn("no_exact_PRECEDES_edges", report["flags"])
        self.assertNotIn("no_PRECEDES_or_equivalent_FOLLOWS_edges", report["flags"])
        self.assertIn("no_exact_CONTRAINDICATES_edges", report["flags"])

    def test_export_provenance_is_not_edge_source_provenance(self):
        graph = snapshot([edge("a", "REQUIRES", "b", source=" ", source_quote="")])
        graph["provenance"] = "Restored backup; not a guideline citation"
        report = inventory_graph(graph)
        props = report["provenance_availability"]["edge_properties"]
        self.assertEqual(props["field_present_counts"]["source"], 1)
        self.assertEqual(props["field_populated_counts"]["source"], 0)
        self.assertIn("no_recognized_source_provenance_fields", report["flags"])

    def test_source_field_availability_is_separate_for_nodes_and_edges(self):
        graph = snapshot([edge("a", "REQUIRES", "b", source_document="guide", source_quote="passage", page=0), edge("b", "REQUIRES", "c")], nodes=[node("a"), node("b", source="guide"), node("c")])
        report = inventory_graph(graph)
        provenance = report["provenance_availability"]
        self.assertEqual(provenance["edge_properties"]["records_with_source_reference_field"], 1)
        self.assertEqual(provenance["edge_properties"]["records_with_source_and_quote_fields"], 1)
        self.assertEqual(provenance["edge_properties"]["records_with_location_field"], 1)
        self.assertEqual(provenance["valid_edges_with_source_field_on_either_endpoint"], 2)
        self.assertIn("incomplete_direct_edge_source_reference_fields", report["flags"])

    def test_duplicate_ids_and_dangling_edges_flag_incompatibility(self):
        graph = snapshot([edge("a", "REQUIRES", "missing")], nodes=[node("a"), node("a")])
        report = inventory_graph(graph)
        self.assertFalse(report["verifier_compatible"])
        self.assertEqual(report["duplicates"]["duplicate_node_id_records"], 1)
        self.assertEqual(report["topology"]["dangling_edge_count"], 1)
        self.assertEqual(report["topology"]["isolated_node_count"], 1)

    def test_extractor_contract_reports_unreachable_predicates_without_mapping(self):
        report = inventory_graph(snapshot([edge("a", "CUSTOM", "b")]), extraction_relation_types=["PRECEDES", "CONTRAINDICATES"])
        self.assertEqual(report["extraction_contract"]["graph_relation_types_outside_extractor"], ["CUSTOM"])
        self.assertEqual(report["extraction_contract"]["stored_edges_outside_extractor"], 1)
        self.assertIn("graph_predicates_outside_extractor_whitelist", report["flags"])

    def test_long_temporal_chain_uses_iterative_analysis(self):
        count = 1500
        graph = snapshot([edge(str(i), "PRECEDES", str(i + 1)) for i in range(count - 1)], nodes=[node(str(i)) for i in range(count)])
        report = inventory_graph(graph)
        self.assertEqual(report["topology"]["weak_component_count"], 1)
        self.assertEqual(report["temporal_order"]["cyclic_component_count"], 0)

    def test_empty_graph_does_not_suggest_measured_quality(self):
        report = inventory_graph(snapshot(nodes=[]))
        self.assertIn("empty_graph", report["flags"])
        self.assertEqual(report["topology"]["weak_component_count"], 0)
        self.assertIsNone(report["human_quality_metrics"])
        self.assertIn("not human validation", render_markdown(report))

    def test_writes_json_and_markdown_with_file_identity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            graph_path, json_path, markdown_path = directory / "graph.json", directory / "report.json", directory / "report.md"
            graph_path.write_text(json.dumps(snapshot()), encoding="utf-8")
            report = write_inventory(graph_path, json_path, markdown_path=markdown_path)
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), report)
            self.assertEqual(len(report["graph_file_sha256"]), 64)
            self.assertTrue(markdown_path.exists())
            self.assertIn("extraction_contract", report)
            with self.assertRaises(ValueError):
                write_inventory(graph_path, json_path)
            with self.assertRaises(ValueError):
                write_inventory(graph_path, graph_path)


if __name__ == "__main__":
    unittest.main()
