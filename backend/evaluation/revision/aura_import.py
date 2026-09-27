"""Import a frozen revision snapshot into an empty Neo4j Aura database.

Credentials are read from an Aura-generated local file and are never copied to
the audit artifacts or printed. The graph is created in one transaction, and a
nonempty database is accepted only when every stored record already matches the
requested snapshot exactly. No clear/delete operation exists in this tool.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from .import_snapshot import WORKSPACE, _fresh_output, read_snapshot


TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED_PREFIX = "_revision_"
REQUIRED_CREDENTIAL_KEYS = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")


def load_aura_credentials(path: str | Path) -> dict:
    source = Path(path).resolve(strict=True)
    values = {}
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"')
        if key in values:
            raise ValueError("Duplicate credential key")
        values[key] = value
    if not all(values.get(key) for key in REQUIRED_CREDENTIAL_KEYS):
        raise ValueError("Aura credential file is missing a required value")
    parsed = urlparse(values["NEO4J_URI"])
    if parsed.scheme != "neo4j+s" or not parsed.hostname or not parsed.hostname.endswith(".databases.neo4j.io"):
        raise ValueError("Expected an encrypted Neo4j Aura URI")
    return {
        "uri": values["NEO4J_URI"],
        "user": values["NEO4J_USERNAME"],
        "password": values["NEO4J_PASSWORD"],
        "database": values["NEO4J_DATABASE"],
        "instance_id": values.get("AURA_INSTANCEID"),
        "instance_name": values.get("AURA_INSTANCENAME"),
        "host": parsed.hostname,
        "credential_file_name": source.name,
    }


def safe_token(value: str) -> str:
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ValueError("Snapshot label or relationship type is not a safe token")
    return value


def _native_value(value):
    if isinstance(value, str) or type(value) is bool:
        return value
    if type(value) is int and -(2**63) <= value < 2**63:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, list) and value:
        kinds = {type(item) for item in value}
        if kinds == {str} or kinds == {bool}:
            return list(value)
        if kinds == {int} and all(-(2**63) <= item < 2**63 for item in value):
            return list(value)
        if kinds == {float} and all(math.isfinite(item) for item in value):
            return list(value)
    return None


def mapped_properties(record: dict, external_id: str, index: int) -> dict:
    output, encoded = {}, []
    for key, value in record.get("properties", {}).items():
        native = _native_value(value)
        if native is None:
            native = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            encoded.append(key)
        output[key] = native
    output.update({
        "_revision_snapshot_id": external_id,
        "_revision_record_index": index,
        "_revision_record_json": json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        "_revision_json_encoded_keys": encoded,
    })
    return output


def prepared_records(snapshot: dict) -> tuple[list[dict], list[dict]]:
    nodes, edges = [], []
    for index, record in enumerate(snapshot["nodes"]):
        labels = tuple(safe_token(label) for label in record.get("labels", []))
        if not labels:
            raise ValueError("Aura import requires at least one label per node")
        nodes.append({"id": record["id"], "labels": labels,
                      "properties": mapped_properties(record, record["id"], index)})
    for index, record in enumerate(snapshot["edges"]):
        identifier = record.get("id", f"_revision_missing_edge_{index}")
        edges.append({"id": identifier, "source": record["source"], "target": record["target"],
                      "type": safe_token(record["type"]),
                      "properties": mapped_properties(record, identifier, index)})
    return nodes, edges


def _counts(session) -> tuple[int, int]:
    nodes = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
    edges = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
    return nodes, edges


def _create_transaction(tx, nodes: list[dict], edges: list[dict]) -> None:
    if tx.run("MATCH (n) RETURN count(n) AS count").single()["count"] != 0:
        raise RuntimeError("Refusing to import into a nonempty Aura database")
    by_labels = defaultdict(list)
    for record in nodes:
        by_labels[record["labels"]].append({"properties": record["properties"]})
    for labels, rows in by_labels.items():
        label_clause = ":".join(f"`{safe_token(label)}`" for label in labels)
        tx.run(f"UNWIND $rows AS row CREATE (n:{label_clause}) SET n = row.properties", rows=rows).consume()
    by_type = defaultdict(list)
    for record in edges:
        by_type[record["type"]].append({"source": record["source"], "target": record["target"],
                                        "properties": record["properties"]})
    for relation_type, rows in by_type.items():
        query = ("UNWIND $rows AS row "
                 "MATCH (source {_revision_snapshot_id: row.source}) "
                 "MATCH (target {_revision_snapshot_id: row.target}) "
                 f"CREATE (source)-[r:`{safe_token(relation_type)}`]->(target) SET r = row.properties")
        tx.run(query, rows=rows).consume()
    actual_nodes = tx.run("MATCH (n) RETURN count(n) AS count").single()["count"]
    actual_edges = tx.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
    if (actual_nodes, actual_edges) != (len(nodes), len(edges)):
        raise RuntimeError("Aura transaction did not create the expected graph cardinality")


def _normalized_properties(value):
    if isinstance(value, dict):
        return {key: _normalized_properties(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalized_properties(item) for item in value]
    return value


def validate_readback(session, snapshot: dict, nodes: list[dict], edges: list[dict]) -> dict:
    actual_nodes = [dict(row) for row in session.run(
        "MATCH (n) RETURN labels(n) AS labels, properties(n) AS properties "
        "ORDER BY n._revision_record_index")]
    if len(actual_nodes) != len(nodes):
        raise RuntimeError("Aura node readback count differs")
    recovered_nodes = []
    for index, (actual, expected) in enumerate(zip(actual_nodes, nodes)):
        if set(actual["labels"]) != set(expected["labels"]):
            raise RuntimeError("Aura node label readback differs")
        if _normalized_properties(actual["properties"]) != _normalized_properties(expected["properties"]):
            raise RuntimeError("Aura node property readback differs")
        recovered = json.loads(actual["properties"]["_revision_record_json"])
        if recovered != snapshot["nodes"][index]:
            raise RuntimeError("Aura lossless node record differs")
        recovered_nodes.append(recovered)
    actual_edges = [dict(row) for row in session.run(
        "MATCH (source)-[r]->(target) "
        "RETURN type(r) AS type, source._revision_snapshot_id AS source, "
        "target._revision_snapshot_id AS target, properties(r) AS properties "
        "ORDER BY r._revision_record_index")]
    if len(actual_edges) != len(edges):
        raise RuntimeError("Aura relationship readback count differs")
    recovered_edges = []
    for index, (actual, expected) in enumerate(zip(actual_edges, edges)):
        if (actual["type"], actual["source"], actual["target"]) != (expected["type"], expected["source"], expected["target"]):
            raise RuntimeError("Aura relationship type or endpoint readback differs")
        if _normalized_properties(actual["properties"]) != _normalized_properties(expected["properties"]):
            raise RuntimeError("Aura relationship property readback differs")
        recovered = json.loads(actual["properties"]["_revision_record_json"])
        if recovered != snapshot["edges"][index]:
            raise RuntimeError("Aura lossless relationship record differs")
        recovered_edges.append(recovered)
    if recovered_nodes != snapshot["nodes"] or recovered_edges != snapshot["edges"]:
        raise RuntimeError("Aura reconstructed snapshot differs")
    return {
        "status": "validated",
        "node_count": len(actual_nodes),
        "edge_count": len(actual_edges),
        "all_labels_endpoints_types_properties_match": True,
        "lossless_records_match": True,
        "label_counts": dict(sorted(Counter(label for node in snapshot["nodes"] for label in node["labels"]).items())),
        "relationship_type_counts": dict(sorted(Counter(edge["type"] for edge in snapshot["edges"]).items())),
    }


def create_name_indexes(session, labels: set[str]) -> dict:
    names = []
    for label in sorted(labels):
        token = safe_token(label)
        name = f"{token.lower()}_name"
        session.run(f"CREATE INDEX `{name}` IF NOT EXISTS FOR (n:`{token}`) ON (n.name)").consume()
        names.append(name)
    deadline = time.monotonic() + 60
    while True:
        states = {row["name"]: row["state"] for row in session.run(
            "SHOW INDEXES YIELD name, state WHERE name IN $names RETURN name, state ORDER BY name", names=names)}
        if set(states) == set(names) and all(state == "ONLINE" for state in states.values()):
            return {"names": names, "states": states}
        if time.monotonic() >= deadline:
            raise RuntimeError("Aura name indexes did not become ONLINE")
        time.sleep(0.5)


def validate_application_contexts(session, snapshot: dict) -> int:
    nodes = {node["id"]: node for node in snapshot["nodes"]}
    expected = defaultdict(lambda: {"anatomy": set(), "instruments": set(), "complications": set(),
                                    "techniques": set(), "medications": set()})
    mapping = {"INVOLVES": "anatomy", "REQUIRES": "instruments", "MAY_CAUSE": "complications",
               "USES_TECHNIQUE": "techniques", "REQUIRES_MEDICATION": "medications"}
    procedures = []
    for node in snapshot["nodes"]:
        if "Procedure" in node["labels"]:
            procedures.append(node["properties"]["name"])
    for edge in snapshot["edges"]:
        if edge["type"] in mapping:
            procedure = nodes[edge["source"]]["properties"]["name"]
            expected[procedure][mapping[edge["type"]]].add(nodes[edge["target"]]["properties"]["name"])
    query = """
        MATCH (p:Procedure {name: $procedure})
        OPTIONAL MATCH (p)-[:INVOLVES]->(a:Anatomy)
        OPTIONAL MATCH (p)-[:REQUIRES]->(i:Instrument)
        OPTIONAL MATCH (p)-[:MAY_CAUSE]->(c:Complication)
        OPTIONAL MATCH (p)-[:USES_TECHNIQUE]->(t:Technique)
        OPTIONAL MATCH (p)-[:REQUIRES_MEDICATION]->(m:Medication)
        RETURN collect(DISTINCT a.name) AS anatomy,
               collect(DISTINCT i.name) AS instruments,
               collect(DISTINCT c.name) AS complications,
               collect(DISTINCT t.name) AS techniques,
               collect(DISTINCT m.name) AS medications
    """
    for procedure in procedures:
        result = session.run(query, procedure=procedure).single()
        if result is None:
            raise RuntimeError("Aura application context is missing a procedure")
        actual = {key: {value for value in result[key] if value is not None} for key in expected[procedure]}
        if actual != expected[procedure]:
            raise RuntimeError("Aura application context differs from the source snapshot")
    return len(procedures)


def configure_backend_env(credentials: dict, output: Path, workspace: Path) -> None:
    from dotenv import dotenv_values, set_key
    workspace = workspace.resolve()
    output = output.resolve()
    private_root = (workspace / "backend/evaluation/revision_outputs").resolve()
    if output != private_root and private_root not in output.parents:
        raise ValueError("Credential backup output must be inside the Git-ignored revision_outputs directory")
    env_file = workspace / "backend/.env"
    if not env_file.is_file():
        raise ValueError("Expected existing backend/.env")
    previous = dotenv_values(env_file)
    backup = output / "previous_backend_neo4j.private.json"
    with backup.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps({key: previous.get(key) for key in
            ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")}, indent=2) + "\n")
    set_key(env_file, "NEO4J_URI", credentials["uri"])
    set_key(env_file, "NEO4J_USER", credentials["user"])
    set_key(env_file, "NEO4J_PASSWORD", credentials["password"])


def import_to_aura(snapshot_path: str | Path, credential_path: str | Path, output_dir: str | Path,
                   *, configure_env: bool = False, workspace: Path = WORKSPACE) -> dict:
    output = _fresh_output(output_dir, workspace)
    source = Path(snapshot_path).resolve(strict=True)
    raw = source.read_bytes()
    snapshot = read_snapshot(raw)
    nodes, edges = prepared_records(snapshot)
    credentials = load_aura_credentials(credential_path)
    output.mkdir(parents=True)
    manifest_path = output / "aura_import_manifest.json"
    manifest = {
        "schema_version": 1,
        "status": "started",
        "snapshot_name": source.name,
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "instance_id": credentials["instance_id"],
        "instance_name": credentials["instance_name"],
        "host": credentials["host"],
        "database": credentials["database"],
        "credential_file_name": credentials["credential_file_name"],
        "credential_values_archived": False,
        "delete_or_clear_operation_available": False,
        "expected_node_count": len(nodes),
        "expected_edge_count": len(edges),
        "backend_env_updated": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    driver = None
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(credentials["uri"], auth=(credentials["user"], credentials["password"]),
                                      connection_timeout=15, connection_acquisition_timeout=30,
                                      max_transaction_retry_time=0)
        driver.verify_connectivity()
        with driver.session(database=credentials["database"]) as session:
            before = _counts(session)
            if before == (0, 0):
                # An explicit, non-retried transaction avoids duplicate CREATEs after
                # an ambiguous commit acknowledgement. A later invocation validates
                # an exact nonempty graph before accepting it.
                with session.begin_transaction() as transaction:
                    _create_transaction(transaction, nodes, edges)
                    transaction.commit()
                imported_now = True
            else:
                imported_now = False
            validation = validate_readback(session, snapshot, nodes, edges)
            indexes = create_name_indexes(session, {label for node in nodes for label in node["labels"]})
            application_contexts = validate_application_contexts(session, snapshot)
        if configure_env:
            configure_backend_env(credentials, output, workspace)
        manifest.update({
            "status": "complete",
            "database_counts_before": {"nodes": before[0], "relationships": before[1]},
            "imported_now": imported_now,
            "validation": validation,
            "indexes": indexes,
            "application_context_procedures_validated": application_contexts,
            "backend_env_updated": configure_env,
            "submission_graph_identity_confirmed": False,
            "purpose": "Hosted copy of the saved-text graph reconstruction; not recovery of the deleted submission database.",
        })
    except Exception as exc:
        manifest.update(status="error", error_type=type(exc).__name__)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if driver is not None:
            driver.close()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--configure-env", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = import_to_aura(args.snapshot, args.credentials, args.output_dir, configure_env=args.configure_env)
    except Exception as exc:
        parser.exit(2, f"error: {type(exc).__name__}; inspect the redacted import manifest\n")
    safe = {key: result[key] for key in ("status", "instance_id", "instance_name", "host", "database",
                                           "expected_node_count", "expected_edge_count", "imported_now",
                                           "validation", "indexes", "backend_env_updated")}
    print(json.dumps(safe, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
