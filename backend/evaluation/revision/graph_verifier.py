"""Deterministic verification against a frozen, explicitly supplied graph snapshot.

This module does not extract relations or infer clinical facts. See
``GRAPH_VERIFIER_FORMAT.md`` for the snapshot, input, and decision semantics.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _name(value: str) -> str:
    return " ".join(value.casefold().split())


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical(source: str, relation: str, target: str) -> tuple[str, str, str]:
    # The sole built-in equivalence: A FOLLOWS B means B PRECEDES A.
    if relation == "FOLLOWS":
        return target, "PRECEDES", source
    return source, relation, target


class FrozenGraph:
    """Validated in-memory snapshot, with exact ID/name/alias resolution.

    Node IDs and predicate tokens are case-sensitive. Names and aliases match
    only after case folding and whitespace normalization. Ambiguity is retained.
    ``opposite_relations`` declares symmetric, same-endpoint predicate opposites.
    It never declares equivalence between predicates.
    """

    def __init__(
        self,
        snapshot: Mapping[str, Any],
        *,
        opposite_relations: Sequence[tuple[str, str]] = (("CONTRAINDICATES", "ALLOWS"),),
    ):
        if not isinstance(snapshot, Mapping):
            raise ValueError("Graph snapshot must be an object")
        self._snapshot = copy.deepcopy(dict(snapshot))
        nodes, edges = self._snapshot.get("nodes"), self._snapshot.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError("Graph snapshot requires nodes and edges lists")
        self._nodes: dict[str, dict] = {}
        self._names: dict[str, set[str]] = defaultdict(set)
        self._edges: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        self._opposites: dict[str, set[str]] = defaultdict(set)

        for node in nodes:
            if not isinstance(node, dict) or not _nonempty(node.get("id")):
                raise ValueError("Every graph node requires a nonempty string id")
            node_id = node["id"]
            if node_id in self._nodes:
                raise ValueError(f"Duplicate graph node id: {node_id}")
            labels, props = node.get("labels", []), node.get("properties", {})
            if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
                raise ValueError(f"Invalid labels for graph node: {node_id}")
            if not isinstance(props, dict):
                raise ValueError(f"Invalid properties for graph node: {node_id}")
            aliases = props.get("aliases", [])
            if not isinstance(aliases, list) or not all(_nonempty(x) for x in aliases):
                raise ValueError(f"Node aliases must be a list of nonempty strings: {node_id}")
            if "name" in props and not _nonempty(props["name"]):
                raise ValueError(f"Node name must be a nonempty string: {node_id}")
            self._nodes[node_id] = node
            names = ([props["name"]] if "name" in props else []) + aliases
            for name in names:
                self._names[_name(name)].add(node_id)

        for index, edge in enumerate(edges):
            if not isinstance(edge, dict) or not all(
                _nonempty(edge.get(key)) for key in ("source", "type", "target")
            ):
                raise ValueError(f"Invalid graph edge at index {index}")
            source, relation, target = edge["source"], edge["type"], edge["target"]
            if relation != relation.strip():
                raise ValueError(f"Predicate tokens must not contain surrounding whitespace: {relation!r}")
            if source not in self._nodes or target not in self._nodes:
                raise ValueError(f"Graph edge {index} refers to an unknown node id")
            if not isinstance(edge.get("properties", {}), dict):
                raise ValueError(f"Invalid properties for graph edge {index}")
            trace = {**copy.deepcopy(edge), "edge_index": index}
            self._edges[_canonical(source, relation, target)].append(trace)

        for pair in opposite_relations:
            if isinstance(pair, (str, bytes)) or not isinstance(pair, Sequence):
                raise ValueError("Explicit predicate opposites must be pairs of nonempty tokens")
            if len(pair) != 2 or not all(_nonempty(x) and x == x.strip() for x in pair):
                raise ValueError("Explicit predicate opposites must be pairs of nonempty tokens")
            left, right = pair
            if left == right or left in {"PRECEDES", "FOLLOWS"} or right in {"PRECEDES", "FOLLOWS"}:
                raise ValueError("Temporal predicates have built-in direction semantics; other opposites must differ")
            self._opposites[left].add(right)
            self._opposites[right].add(left)
        self.opposite_relations = tuple(sorted({tuple(sorted((left, right))) for left, rights in self._opposites.items() for right in rights}))

        encoded = json.dumps(self._snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, path: str | Path, **kwargs: Any) -> "FrozenGraph":
        with Path(path).open(encoding="utf-8-sig") as handle:
            return cls(json.load(handle), **kwargs)

    def resolve(self, reference: str) -> dict[str, Any]:
        """Return a unique node or an explicit unresolved/ambiguous result."""
        if reference in self._nodes:
            return {"status": "resolved", "node_id": reference, "matched_by": "id", "candidates": [reference]}
        candidates = sorted(self._names.get(_name(reference), ()))
        if len(candidates) == 1:
            return {"status": "resolved", "node_id": candidates[0], "matched_by": "name_or_alias", "candidates": candidates}
        return {"status": "ambiguous" if candidates else "unresolved", "node_id": None, "matched_by": None, "candidates": candidates}

    def evidence(self, triple: tuple[str, str, str]) -> tuple[list[dict], list[dict]]:
        """Return original supported/opposing edges, retaining edge provenance."""
        source, relation, target = triple
        opposite_keys = {(source, other, target) for other in self._opposites.get(relation, ())}
        if relation == "PRECEDES":
            opposite_keys.add((target, relation, source))
        matches = self._edges.get(triple, [])
        opposites = [edge for key in sorted(opposite_keys) for edge in self._edges.get(key, [])]
        return copy.deepcopy(matches), copy.deepcopy(opposites)


def _threshold(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number in [0, 1]")


def _decision(graph: FrozenGraph, claim: Mapping[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(dict(claim))
    result = {
        "claim": original,
        "provenance": [original],
        "required": claim.get("required", True),
        "state": "unknown",
        "conflict": False,
        "canonical_relation": None,
        "resolution": {},
        "matched_edges": [],
        "opposing_edges": [],
        "reason": "invalid_claim",
    }
    if not all(_nonempty(claim.get(key)) for key in ("source", "relation", "target", "evidence_quote", "chunk_id")):
        return result
    if not isinstance(result["required"], bool) or claim["relation"] != claim["relation"].strip():
        return result
    source, target = graph.resolve(claim["source"]), graph.resolve(claim["target"])
    result["resolution"] = {"source": source, "target": target}
    if source["status"] != "resolved" or target["status"] != "resolved":
        result["reason"] = "ambiguous_entity" if "ambiguous" in (source["status"], target["status"]) else "unresolved_entity"
        return result
    triple = _canonical(source["node_id"], claim["relation"], target["node_id"])
    result["canonical_relation"] = dict(zip(("source", "relation", "target"), triple))
    supported, opposed = graph.evidence(triple)
    result["matched_edges"], result["opposing_edges"] = supported, opposed
    if supported and opposed:
        # Three-state report: conflict is a contradicted relation with an extra flag.
        result.update(state="contradicted", conflict=True, reason="graph_conflict")
    elif opposed:
        result.update(state="contradicted", reason="explicit_opposite")
    elif supported:
        result.update(state="supported", reason="directed_typed_edge")
    else:
        result["reason"] = "edge_absent"
    return result


def verify_claims(
    graph: FrozenGraph,
    claims: Sequence[Mapping[str, Any]],
    *,
    min_support: float = 1.0,
    min_coverage: float = 1.0,
    hard_contradiction_veto: bool = True,
) -> dict[str, Any]:
    """Verify supplied assertions; empty or entirely unknown evidence cannot certify.

    Repeated canonical assertions within a chunk count once; every input assertion
    remains in provenance and a duplicate marked required makes its group required.
    Conflicting graph edges always veto, including in the soft-only ablation.
    """
    _threshold(min_support, "min_support")
    _threshold(min_coverage, "min_coverage")
    if not isinstance(hard_contradiction_veto, bool):
        raise ValueError("hard_contradiction_veto must be a boolean")
    if isinstance(claims, (str, bytes)) or not isinstance(claims, Sequence):
        raise ValueError("claims must be a sequence of objects")
    decisions: list[dict] = []
    seen: dict[tuple, dict] = {}
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise ValueError("Every expected claim must be an object")
        decision = _decision(graph, claim)
        canonical = decision["canonical_relation"]
        key = (
            claim.get("chunk_id"), canonical["source"], canonical["relation"], canonical["target"]
        ) if canonical else None
        if key is not None and key in seen:
            prior = seen[key]
            prior["provenance"].extend(decision["provenance"])
            prior["required"] = prior["required"] or decision["required"]
        else:
            decisions.append(decision)
            if key is not None:
                seen[key] = decision
    counts = {state: sum(d["state"] == state for d in decisions) for state in ("supported", "contradicted", "unknown")}
    total = len(decisions)
    known = counts["supported"] + counts["contradicted"]
    score = counts["supported"] / known if known else None
    coverage = known / total if total else 0.0
    conflicts = sum(d["conflict"] for d in decisions)
    required_contradiction = any(d["state"] == "contradicted" and d["required"] for d in decisions)
    veto = bool(conflicts or (hard_contradiction_veto and required_contradiction))
    if not total:
        reason = "empty_expected_relations"
    elif conflicts:
        reason = "graph_conflict"
    elif veto:
        reason = "required_relation_contradicted"
    elif coverage < min_coverage:
        reason = "insufficient_graph_coverage"
    elif score is None or score < min_support:
        reason = "insufficient_relation_support"
    else:
        reason = "verification_criteria_satisfied"
    return {
        "graph_checksum": graph.checksum,
        "decisions": decisions,
        "counts": counts,
        "input_claim_count": len(claims),
        "expected_relation_count": total,
        "conflict_count": conflicts,
        "support_score": score,
        "coverage": coverage,
        "contradiction_veto": veto,
        "eligible_to_answer": reason == "verification_criteria_satisfied",
        "reason": reason,
        "policy": {"min_support": min_support, "min_coverage": min_coverage, "hard_contradiction_veto": hard_contradiction_veto, "conflict_veto": True, "opposite_relations": [list(pair) for pair in graph.opposite_relations]},
    }


def gate_chunks(
    graph: FrozenGraph,
    chunks: Sequence[Mapping[str, Any]],
    claims_by_chunk: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    min_support: float = 1.0,
    min_coverage: float = 1.0,
    hard_contradiction_veto: bool = True,
) -> dict[str, Any]:
    """Return only certified chunks for pre-generation evidence assembly.

    The caller must pass ``retained_chunks`` to generation. This module does not
    call a generator. Query eligibility means at least one chunk passed; it does
    not assert that the retained evidence completely answers the user's query.
    """
    _threshold(min_support, "min_support")
    _threshold(min_coverage, "min_coverage")
    if not isinstance(hard_contradiction_veto, bool):
        raise ValueError("hard_contradiction_veto must be a boolean")
    if not isinstance(claims_by_chunk, Mapping):
        raise ValueError("claims_by_chunk must map chunk IDs to claim lists")
    if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence) or not all(isinstance(chunk, Mapping) for chunk in chunks):
        raise ValueError("chunks must be a sequence of objects")
    chunk_ids = [chunk.get("chunk_id") for chunk in chunks]
    if not all(_nonempty(value) for value in chunk_ids) or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("Chunks require unique nonempty string chunk_id values")
    if set(claims_by_chunk) - set(chunk_ids):
        raise ValueError("Claims refer to chunks outside the candidate set")
    retained, rejected, reports = [], [], {}
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        claims = claims_by_chunk.get(chunk_id, [])
        if isinstance(claims, (str, bytes)) or not isinstance(claims, Sequence) or not all(isinstance(claim, Mapping) for claim in claims):
            raise ValueError("Every chunk's claims must be a sequence of objects")
        if any(claim.get("chunk_id") != chunk_id for claim in claims):
            raise ValueError(f"Claim chunk_id differs from containing candidate: {chunk_id}")
        report = verify_claims(
            graph, claims, min_support=min_support, min_coverage=min_coverage,
            hard_contradiction_veto=hard_contradiction_veto,
        )
        reports[chunk_id] = report
        (retained if report["eligible_to_answer"] else rejected).append(copy.deepcopy(dict(chunk)))
    return {
        "retained_chunks": retained,
        "rejected_chunks": rejected,
        "chunk_reports": reports,
        "eligible_to_answer": bool(retained),
        "reason": "retained_evidence_available" if retained else "no_certified_chunks",
        "aggregation_rule": "retain_each_passing_chunk; query_eligible_iff_at_least_one_retained",
    }
