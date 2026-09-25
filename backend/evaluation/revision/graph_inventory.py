"""Inventory an offline graph snapshot; structure is not human graph validation."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

from .graph_verifier import FrozenGraph


SOURCE_FIELDS = frozenset({"source", "sources", "source_document", "source_documents", "source_id",
    "source_url", "source_uri", "document_id", "document", "guideline_id", "guideline",
    "citation", "reference", "references", "filename"})
QUOTE_FIELDS = frozenset({"source_quote", "evidence_quote", "source_text", "evidence_text", "quote", "text_span", "source_span"})
LOCATION_FIELDS = frozenset({"page", "page_number", "chunk_id", "chunk_index", "span_start", "span_end", "offset"})


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _name(value: str) -> str:
    return " ".join(value.casefold().split())


def _present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return any(_present(item) for item in (value.values() if isinstance(value, dict) else value))
    return value is not None and value is not False


def _has(properties: dict, fields: frozenset[str]) -> bool:
    return any(_present(properties.get(field)) for field in fields)


def _properties(records: list[dict]) -> dict:
    present, populated = Counter(), Counter()
    for record in records:
        for key, value in record.get("properties", {}).items():
            present[key] += 1
            populated[key] += int(_present(value))
    return {
        "field_present_counts": dict(sorted(present.items())),
        "field_populated_counts": dict(sorted(populated.items())),
        "records_with_source_reference_field": sum(_has(r.get("properties", {}), SOURCE_FIELDS) for r in records),
        "records_with_quote_field": sum(_has(r.get("properties", {}), QUOTE_FIELDS) for r in records),
        "records_with_location_field": sum(_has(r.get("properties", {}), LOCATION_FIELDS) for r in records),
        "records_with_source_and_quote_fields": sum(_has(r.get("properties", {}), SOURCE_FIELDS) and _has(r.get("properties", {}), QUOTE_FIELDS) for r in records),
    }


def _weak_components(node_ids: set[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    adjacent = {node: set() for node in node_ids}
    for source, target in edges:
        adjacent[source].add(target)
        adjacent[target].add(source)
    pending, components = set(node_ids), []
    while pending:
        start = min(pending)
        stack, component = [start], []
        pending.remove(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for other in sorted(adjacent[node]):
                if other in pending:
                    pending.remove(other)
                    stack.append(other)
        components.append(sorted(component))
    return sorted(components, key=lambda group: (-len(group), group))


def _strong_components(nodes: set[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    """Iterative Kosaraju traversal; supports graphs larger than recursion limits."""
    forward, reverse = {node: set() for node in nodes}, {node: set() for node in nodes}
    for source, target in edges:
        forward[source].add(target)
        reverse[target].add(source)
    visited, order = set(), []
    for start in sorted(nodes):
        stack = [(start, False)]
        while stack:
            node, finished = stack.pop()
            if finished:
                order.append(node)
            elif node not in visited:
                visited.add(node)
                stack.append((node, True))
                stack.extend((other, False) for other in sorted(forward[node], reverse=True) if other not in visited)
    visited, components = set(), []
    for start in reversed(order):
        if start in visited:
            continue
        stack, component = [start], []
        visited.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for other in sorted(reverse[node]):
                if other not in visited:
                    visited.add(other)
                    stack.append(other)
        components.append(sorted(component))
    return sorted(components, key=lambda group: (-len(group), group))


def inventory_graph(snapshot: dict, *, sample_limit: int = 20, extraction_relation_types=None) -> dict:
    """Count stored records and exact structural relationships, without inference.

    Duplicate node IDs and dangling edges are reported as verifier incompatibility.
    Topology uses unique IDs and excludes dangling edges; no invalid record is
    silently repaired. Source-field counts measure availability, not correctness.
    """
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or sample_limit < 1:
        raise ValueError("sample_limit must be a positive integer")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("nodes"), list) or not isinstance(snapshot.get("edges"), list):
        raise ValueError("Snapshot requires nodes and edges lists")
    nodes, edges = snapshot["nodes"], snapshot["edges"]
    for kind, records, fields in (("node", nodes, ("id",)), ("edge", edges, ("source", "type", "target"))):
        for record in records:
            if not isinstance(record, dict) or not all(isinstance(record.get(k), str) and record[k].strip() for k in fields) or not isinstance(record.get("properties", {}), dict):
                raise ValueError(f"Malformed {kind} record")
    for node in nodes:
        if not isinstance(node.get("labels", []), list) or not all(isinstance(label, str) for label in node.get("labels", [])):
            raise ValueError("Malformed node labels")
    encoded = _json(snapshot).encode("utf-8")
    compatibility_error = None
    try:
        FrozenGraph(snapshot)
    except ValueError as exc:
        compatibility_error = str(exc)

    ids = Counter(node["id"] for node in nodes)
    node_ids = set(ids)
    node_by_id = {node["id"]: node for node in nodes}
    names, mentions = defaultdict(set), defaultdict(set)
    missing_names = 0
    for node in nodes:
        props, node_id = node.get("properties", {}), node["id"]
        name = props.get("name")
        if isinstance(name, str) and name.strip():
            names[_name(name)].add(node_id)
            mentions[_name(name)].add(node_id)
        else:
            missing_names += 1
        aliases = props.get("aliases", [])
        for alias in aliases if isinstance(aliases, list) else []:
            if isinstance(alias, str) and alias.strip():
                mentions[_name(alias)].add(node_id)
    ambiguous_names = {name: sorted(values) for name, values in names.items() if len(values) > 1}
    ambiguous_mentions = {name: sorted(values) for name, values in mentions.items() if len(values) > 1}
    relations = Counter(edge["type"] for edge in edges)
    triples = Counter((e["source"], e["type"], e["target"]) for e in edges)
    canonical = Counter((e["target"], "PRECEDES", e["source"]) if e["type"] == "FOLLOWS" else (e["source"], e["type"], e["target"]) for e in edges)
    same_properties = Counter(_json([e["source"], e["type"], e["target"], e.get("properties", {})]) for e in edges)
    valid_edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
    dangling = [i for i, e in enumerate(edges) if e["source"] not in node_ids or e["target"] not in node_ids]
    pairs = {(e["source"], e["target"]) for e in valid_edges}
    incident = {node for pair in pairs for node in pair}
    components = _weak_components(node_ids, pairs)
    temporal = {(target, source) if relation == "FOLLOWS" else (source, target)
                for source, relation, target in triples if relation in {"PRECEDES", "FOLLOWS"} and source in node_ids and target in node_ids}
    temporal_nodes = {node for pair in temporal for node in pair}
    temporal_components = _strong_components(temporal_nodes, temporal)
    cycles = [group for group in temporal_components if len(group) > 1 or (group[0], group[0]) in temporal]
    reverse_pairs = sorted({tuple(sorted((source, target))) for source, target in temporal if (target, source) in temporal})
    contraindication_conflicts = sorted((source, target) for source, relation, target in triples
        if relation == "CONTRAINDICATES" and (source, "ALLOWS", target) in triples)
    edge_provenance, node_provenance = _properties(edges), _properties(nodes)
    endpoint_source_count = sum(any(_has(node_by_id[endpoint].get("properties", {}), SOURCE_FIELDS) for endpoint in (e["source"], e["target"])) for e in valid_edges)
    flags = []
    if not nodes:
        flags.append("empty_graph")
    if not edges:
        flags.append("no_edges")
    if not relations["PRECEDES"]:
        flags.append("no_exact_PRECEDES_edges")
    if not temporal:
        flags.append("no_PRECEDES_or_equivalent_FOLLOWS_edges")
    if not relations["CONTRAINDICATES"]:
        flags.append("no_exact_CONTRAINDICATES_edges")
    if not edge_provenance["records_with_source_reference_field"]:
        flags.append("no_direct_edge_source_reference_fields")
    if not edge_provenance["records_with_source_reference_field"] and not node_provenance["records_with_source_reference_field"]:
        flags.append("no_recognized_source_provenance_fields")
    if edges and edge_provenance["records_with_source_reference_field"] < len(edges):
        flags.append("incomplete_direct_edge_source_reference_fields")
    if ambiguous_mentions:
        flags.append("ambiguous_entity_names_or_aliases")
    if cycles:
        flags.append("temporal_cycles_present")
    if reverse_pairs or contraindication_conflicts:
        flags.append("explicit_graph_conflicts_present")
    if compatibility_error:
        flags.append("snapshot_incompatible_with_verifier")
    report = {
        "schema_version": 1, "report_kind": "structural_inventory_not_human_validation",
        "graph_sha256": hashlib.sha256(encoded).hexdigest(),
        "snapshot_provenance": snapshot.get("provenance"),
        "submission_graph_identity_confirmed": False,
        "node_count": len(nodes), "unique_node_ids": len(node_ids), "edge_count": len(edges),
        "node_label_counts": dict(sorted(Counter(label for node in nodes for label in set(node.get("labels", []))).items())),
        "unlabeled_node_count": sum(not node.get("labels") for node in nodes),
        "relation_type_counts": dict(sorted(relations.items())),
        "verifier_compatible": compatibility_error is None, "verifier_validation_error": compatibility_error,
        "duplicates": {
            "duplicate_node_id_records": sum(count - 1 for count in ids.values()),
            "duplicate_node_ids_sample": sorted(key for key, count in ids.items() if count > 1)[:sample_limit],
            "unique_exact_typed_triples": len(triples),
            "parallel_exact_triple_extra_edges": sum(count - 1 for count in triples.values()),
            "same_triple_and_properties_extra_edges": sum(count - 1 for count in same_properties.values()),
            "unique_canonical_typed_triples": len(canonical),
            "canonical_triple_extra_edges": sum(count - 1 for count in canonical.values()),
            "definition": "Edges with different IDs can duplicate a typed triple; same-properties comparison ignores edge IDs. Canonical form reverses FOLLOWS to PRECEDES only.",
        },
        "entity_resolution": {
            "nodes_without_nonempty_name": missing_names,
            "ambiguous_normalized_name_count": len(ambiguous_names),
            "ambiguous_name_or_alias_count": len(ambiguous_mentions),
            "ambiguous_name_or_alias_samples": [{"mention": name, "node_ids": values[:sample_limit], "node_count": len(values)} for name, values in sorted(ambiguous_mentions.items())[:sample_limit]],
            "normalization": "case folding and whitespace normalization; exact IDs take precedence; no fuzzy synonyms",
        },
        "provenance_availability": {
            "edge_properties": edge_provenance, "node_properties": node_provenance,
            "valid_edges_with_source_field_on_either_endpoint": endpoint_source_count,
            "recognized_source_fields": sorted(SOURCE_FIELDS), "recognized_quote_fields": sorted(QUOTE_FIELDS),
            "recognized_location_fields": sorted(LOCATION_FIELDS),
            "interpretation": "Nonempty field presence only; no source authenticity, entailment, correctness, or human validation established. Top-level export provenance is not guideline provenance. Endpoint references do not establish a source for each relation. Unrecognized or nested provenance requires separate inspection.",
        },
        "topology": {
            "weak_component_count": len(components), "weak_component_sizes": [len(group) for group in components],
            "isolated_node_count": len(node_ids - incident), "isolated_node_ids_sample": sorted(node_ids - incident)[:sample_limit],
            "self_loop_edge_count": sum(e["source"] == e["target"] for e in valid_edges),
            "dangling_edge_count": len(dangling), "dangling_edge_indices_sample": dangling[:sample_limit],
            "definition": "Weak components ignore direction and relation type, include isolated unique node IDs, and exclude dangling edges.",
        },
        "temporal_order": {
            "exact_PRECEDES_edge_count": relations["PRECEDES"], "exact_FOLLOWS_edge_count": relations["FOLLOWS"],
            "unique_canonical_PRECEDES_pairs": len(temporal), "cyclic_component_count": len(cycles),
            "nodes_in_cyclic_components": sum(len(group) for group in cycles),
            "cyclic_components_sample": [{"node_count": len(group), "node_ids": group[:sample_limit]} for group in cycles[:sample_limit]],
            "direct_reverse_conflict_count": len(reverse_pairs),
            "direct_reverse_conflicts_sample": [list(pair) for pair in reverse_pairs[:sample_limit]],
            "definition": "Cyclic components are strongly connected components with >1 node or a self-loop, not the number of all simple cycles. FOLLOWS is reversed to PRECEDES. The checker detects direct opposites, not transitive cycles.",
        },
        "explicit_opposites": {
            "predicate_pairs": [["CONTRAINDICATES", "ALLOWS"]],
            "same_endpoint_conflict_count": len(contraindication_conflicts),
            "conflicts_sample": [{"source": source, "target": target} for source, target in contraindication_conflicts[:sample_limit]],
            "interpretation": "Exact predicates at identical ordered endpoints only. CONTRAINDICATED_WITH is not mapped to CONTRAINDICATES.",
        },
        "flags": flags, "sample_limit": sample_limit,
        "human_quality_metrics": None,
        "limitations": "No clinical accuracy, precision, recall, coverage of guidelines, or calibration can be inferred from this inventory. Counts describe the supplied snapshot; submission-time identity requires author confirmation.",
    }
    if extraction_relation_types is not None:
        declared = set(extraction_relation_types)
        if not all(isinstance(value, str) and value for value in declared):
            raise ValueError("Extraction relation types must be nonempty strings")
        unsupported = sorted(set(relations) - declared)
        report["extraction_contract"] = {
            "declared_relation_types": sorted(declared),
            "graph_relation_types_outside_extractor": unsupported,
            "stored_edges_outside_extractor": sum(relations[relation] for relation in unsupported),
            "extractor_types_without_exact_graph_edges": sorted(declared - set(relations)),
            "interpretation": "Exact token comparison; absent PRECEDES can still be represented by reversed FOLLOWS. A whitelist mismatch is an implementation-coverage limitation, not an erroneous graph edge.",
        }
        if unsupported:
            flags.append("graph_predicates_outside_extractor_whitelist")
    return report


def render_markdown(report: dict) -> str:
    lines = ["# Graph snapshot inventory", "", "This is a structural audit, not human validation of clinical correctness.", "",
        f"- Nodes: {report['node_count']} records ({report['unique_node_ids']} unique IDs).",
        f"- Edges: {report['edge_count']} records; {report['duplicates']['unique_exact_typed_triples']} unique directed typed triples.",
        f"- Weak components: {report['topology']['weak_component_count']}; isolated nodes: {report['topology']['isolated_node_count']}.",
        f"- Edges with recognized source-reference fields: {report['provenance_availability']['edge_properties']['records_with_source_reference_field']}/{report['edge_count']}.",
        f"- Temporal cyclic components: {report['temporal_order']['cyclic_component_count']}; direct temporal conflicts: {report['temporal_order']['direct_reverse_conflict_count']}.",
        f"- Explicit same-endpoint predicate conflicts: {report['explicit_opposites']['same_endpoint_conflict_count']}.",
        f"- Ambiguous names or aliases: {report['entity_resolution']['ambiguous_name_or_alias_count']}.", "", "| Relation type | Stored edges |", "|---|---:|"]
    lines.extend(f"| {relation.replace('|', '&#124;')} | {count} |" for relation, count in report["relation_type_counts"].items())
    lines.extend(["", "Flags: " + (", ".join(f"`{flag}`" for flag in report["flags"]) or "none from these structural checks"), "", report["limitations"], ""])
    return "\n".join(lines)


def write_inventory(graph_path: str | Path, output_json: str | Path, *, markdown_path: str | Path | None = None, sample_limit: int = 20) -> dict:
    from .run_matched import RELATION_TYPES

    graph_path, output_json = Path(graph_path), Path(output_json)
    outputs = [output_json] + ([Path(markdown_path)] if markdown_path is not None else [])
    if len({path.resolve() for path in [graph_path, *outputs]}) != len(outputs) + 1:
        raise ValueError("Input graph and output paths must differ")
    if any(path.exists() for path in outputs):
        raise ValueError("Inventory output already exists; choose new paths")
    raw = graph_path.read_bytes()
    report = inventory_graph(json.loads(raw.decode("utf-8-sig")), sample_limit=sample_limit, extraction_relation_types=RELATION_TYPES)
    report["graph_file_sha256"] = hashlib.sha256(raw).hexdigest()
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    if markdown_path is not None:
        with Path(markdown_path).open("x", encoding="utf-8") as handle:
            handle.write(render_markdown(report))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--sample-limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        report = write_inventory(args.graph, args.output, markdown_path=args.markdown, sample_limit=args.sample_limit)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({key: report[key] for key in ("node_count", "edge_count", "relation_type_counts", "flags", "verifier_compatible")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
