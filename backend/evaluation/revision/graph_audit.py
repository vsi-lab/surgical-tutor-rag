"""Export a reproducible, relation-stratified graph sample for human review.

Sampling records is automated. Judgments of entailment, clinical relations,
direction and normalization remain blank for qualified human reviewers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from .graph_verifier import FrozenGraph


GRAPH_LABEL_FIELDS = ("source_entails", "relation_correct", "direction_correct", "normalization_correct")
GRAPH_CSV_FIELDS = (
    "sample_id", "source_node", "relation", "target_node", "edge_properties",
    "annotator_id", *GRAPH_LABEL_FIELDS, "source_citation", "comments",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def export_graph_sample(
    graph_path: str | Path,
    output_csv: str | Path,
    manifest_path: str | Path,
    *,
    per_relation: int = 25,
    seed: int = 2026,
) -> dict[str, Any]:
    """Uniformly sample up to per_relation edges within every relation stratum.

    This is a sample of stored edge records, not a sample of unique semantic
    facts. The manifest preserves edge indices and graph identity. No accuracy,
    precision, clinical correctness, or recall is inferred from structure.
    """
    if isinstance(per_relation, bool) or not isinstance(per_relation, int) or per_relation < 1:
        raise ValueError("per_relation must be a positive integer")
    graph_path, output_csv, manifest_path = map(Path, (graph_path, output_csv, manifest_path))
    if len({path.resolve() for path in (graph_path, output_csv, manifest_path)}) != 3:
        raise ValueError("Graph input, sample CSV and manifest need different paths")
    if output_csv.exists() or manifest_path.exists():
        raise ValueError("Graph annotation outputs already exist; choose new paths")
    graph_bytes = graph_path.read_bytes()
    snapshot = json.loads(graph_bytes.decode("utf-8-sig"))
    graph = FrozenGraph(snapshot)
    _canonical_json(snapshot)  # Reject non-finite numbers even in arbitrary properties.
    nodes = {node["id"]: node for node in snapshot["nodes"]}
    strata: dict[str, list[int]] = defaultdict(list)
    for index, edge in enumerate(snapshot["edges"]):
        strata[edge["type"]].append(index)
    if not strata:
        raise ValueError("Cannot annotate edge quality: the snapshot has no edges")
    rng = random.Random(seed)
    indices = []
    for relation in sorted(strata):
        indices.extend(rng.sample(strata[relation], min(per_relation, len(strata[relation]))))
    rng.shuffle(indices)
    rows, items = [], []
    for index in indices:
        edge = snapshot["edges"][index]
        sample_id = f"g_{rng.getrandbits(128):032x}"
        rows.append({
            **{field: "" for field in GRAPH_CSV_FIELDS},
            "sample_id": sample_id,
            "source_node": _canonical_json(nodes[edge["source"]]),
            "relation": edge["type"],
            "target_node": _canonical_json(nodes[edge["target"]]),
            "edge_properties": _canonical_json(edge.get("properties", {})),
        })
        items.append({"sample_id": sample_id, "edge_index": index, "edge_id": edge.get("id"), "relation": edge["type"]})
    manifest = {
        "schema_version": 1,
        "graph_sha256": graph.checksum,
        "graph_file_sha256": hashlib.sha256(graph_bytes).hexdigest(),
        "graph_provenance": snapshot.get("provenance"),
        "submission_graph_identity_confirmed": False,
        "seed": seed,
        "maximum_edges_per_relation": per_relation,
        "sampling_unit": "stored edge record; duplicate semantic facts are not silently removed",
        "sampling_method": "simple random sampling without replacement within each exact relation-type stratum",
        "node_count": len(nodes),
        "edge_count": len(snapshot["edges"]),
        "sample_size": len(items),
        "strata": {relation: {"population": len(indices_for_type), "sample": min(per_relation, len(indices_for_type))} for relation, indices_for_type in sorted(strata.items())},
        "human_annotation_status": "pending",
        "graph_quality_estimates": None,
        "items": items,
    }
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GRAPH_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--per-relation", type=int, default=25)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    try:
        result = export_graph_sample(args.graph, args.output, args.manifest, per_relation=args.per_relation, seed=args.seed)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({key: value for key, value in result.items() if key != "items"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
