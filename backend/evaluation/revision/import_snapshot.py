"""Build a fresh isolated Neo4j database and importable dump from a frozen snapshot.

No existing Desktop instance, database, password, or configuration is accessed.
Unsupported native property values remain recoverable through explicit JSON
encoding and a lossless copy of every original node/edge record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any


RESERVED_PREFIX = "_revision_"
WORKSPACE = Path(__file__).resolve().parents[3]


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def read_snapshot(raw: bytes) -> dict:
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=reject_constant)
    validate_snapshot(value)
    return value


def validate_snapshot(snapshot: Any) -> None:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("nodes"), list) or not isinstance(snapshot.get("edges"), list):
        raise ValueError("Snapshot requires nodes and edges lists")
    # Also rejects overflow such as 1e999 that a JSON parser turns into infinity.
    json.dumps(snapshot, allow_nan=False)
    node_ids, edge_ids = set(), set()
    for kind, records, fields in (("node", snapshot["nodes"], ("id",)), ("edge", snapshot["edges"], ("source", "target", "type"))):
        for index, record in enumerate(records):
            if not isinstance(record, dict) or not all(isinstance(record.get(field), str) and record[field].strip() for field in fields):
                raise ValueError(f"Malformed {kind} at index {index}")
            props = record.get("properties", {})
            if not isinstance(props, dict) or any(not isinstance(key, str) or not key or key.startswith(RESERVED_PREFIX) for key in props):
                raise ValueError(f"Invalid or reserved {kind} property key at index {index}")
            if kind == "node":
                labels = record.get("labels", [])
                if not isinstance(labels, list) or not all(isinstance(label, str) and label.strip() for label in labels) or len(set(labels)) != len(labels):
                    raise ValueError(f"Node labels must be unique nonempty strings at index {index}")
                if record["id"] in node_ids:
                    raise ValueError("Duplicate node ID")
                node_ids.add(record["id"])
            else:
                identifier = record.get("id", f"_revision_missing_edge_{index}")
                if not isinstance(identifier, str) or not identifier.strip() or identifier in edge_ids:
                    raise ValueError("Invalid or duplicate edge ID")
                edge_ids.add(identifier)
                if record["source"] not in node_ids or record["target"] not in node_ids:
                    raise ValueError("Dangling edge endpoint")


def _fresh_output(path: str | Path, workspace: Path) -> Path:
    requested = Path(path)
    if requested.is_symlink():
        raise ValueError("Output must not be a symbolic link")
    output, workspace = requested.resolve(), workspace.resolve()
    if output == workspace or workspace not in output.parents:
        raise ValueError("Output must be a fresh subdirectory inside the repository workspace")
    if output.relative_to(workspace).parts[0] in {".git", ".codex", ".agents"}:
        raise ValueError("Output must not be inside workspace control directories")
    if output.exists():
        raise ValueError("Output already exists; no overwrites or removals are allowed")
    return output


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _run_step(command: list[str], output: Path, name: str, env: dict, timeout: int) -> None:
    with (output / f"{name}_stdout.txt").open("x", encoding="utf-8") as stdout, (output / f"{name}_stderr.txt").open("x", encoding="utf-8") as stderr:
        result = subprocess.run(command, cwd=output, stdout=stdout, stderr=stderr, env=env, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{name} exited {result.returncode}; see {name}_stderr.txt")


def import_snapshot(snapshot_path: str | Path, output_dir: str | Path, *, neo4j_home: str | Path,
                    java_home: str | Path, step_timeout: int = 300, workspace: Path = WORKSPACE) -> dict:
    if isinstance(step_timeout, bool) or not isinstance(step_timeout, int) or not 1 <= step_timeout <= 1800:
        raise ValueError("step_timeout must be an integer from 1 to 1800 seconds")
    output = _fresh_output(output_dir, workspace)
    source = Path(snapshot_path).resolve(strict=True)
    distribution, jdk = Path(neo4j_home).resolve(strict=True), Path(java_home).resolve(strict=True)
    suffix = ".exe" if os.name == "nt" else ""
    java, javac = jdk / "bin" / f"java{suffix}", jdk / "bin" / f"javac{suffix}"
    if not source.is_file() or not java.is_file() or not javac.is_file() or not (distribution / "lib").is_dir():
        raise ValueError("Snapshot, Java executables, or Neo4j library directory not found")
    raw = source.read_bytes()
    snapshot = read_snapshot(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    helper = Path(__file__).with_name("SnapshotGraphImport.java")
    # Resolve all inputs and validate the entire snapshot before creating anything.
    helper_hash = hashlib.sha256(helper.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    for name in ("conf", "data", "logs", "run", "importer_classes", "dump"):
        (output / name).mkdir()
    (output / "input_snapshot.json").write_bytes(raw)
    (output / ".revision-snapshot-import").write_text(source_hash + "\n", encoding="utf-8")
    (output / "conf" / "neo4j.conf").write_text(
        "server.memory.heap.initial_size=256m\nserver.memory.heap.max_size=512m\n"
        "server.memory.pagecache.size=128m\nserver.bolt.enabled=false\n"
        "server.http.enabled=false\nserver.https.enabled=false\n", encoding="utf-8")
    manifest = {
        "schema_version": 1, "status": "started", "input_snapshot_name": source.name,
        "input_snapshot_sha256": source_hash,
        "snapshot_content_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(),
        "node_count": len(snapshot["nodes"]), "edge_count": len(snapshot["edges"]),
        "neo4j_distribution": distribution.name, "jdk": jdk.name,
        "java_helper_sha256": helper_hash, "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "existing_instance_accessed": False, "submission_graph_identity_confirmed": False,
        "client_connectors_enabled": False, "database_stopped_after_import": None,
        "property_encoding": "Native scalars and homogeneous nonempty arrays; other values JSON strings under original keys, listed in _revision_json_encoded_keys. _revision_record_json preserves each complete input record. _revision_snapshot_id retains external IDs; missing edge IDs use _revision_missing_edge_<index>.",
        "purpose": "Import of the provided reconstruction snapshot; this does not validate clinical facts or reproduce an unavailable historical graph.",
    }
    manifest_path = output / "import_manifest.json"
    _write_json(manifest_path, manifest)
    env = dict(os.environ, JAVA_HOME=str(jdk), NEO4J_HOME=str(output), NEO4J_CONF=str(output / "conf"))
    libraries, classes = str(distribution / "lib" / "*"), output / "importer_classes"
    current_step = "compile"
    try:
        _run_step([str(javac), "-cp", libraries, "-d", str(classes), str(helper)], output, current_step, env, step_timeout)
        current_step = "import"
        _run_step([str(java), "-Xmx512m", "--add-opens=java.base/java.nio=ALL-UNNAMED", "--add-opens=java.base/java.lang=ALL-UNNAMED",
                   "-cp", str(classes) + os.pathsep + libraries, "SnapshotGraphImport", str(output), str(output / "input_snapshot.json")],
                  output, current_step, env, step_timeout)
        validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        recovered = read_snapshot((output / "readback_snapshot.json").read_bytes())
        expected = {"status": "validated", "input_snapshot_sha256": source_hash, "node_count": len(snapshot["nodes"]),
                    "edge_count": len(snapshot["edges"]), "all_labels_endpoints_types_properties_match": True,
                    "lossless_records_match": True, "database_shutdown_before_validation_output": True, "client_connectors_enabled": False}
        if recovered != snapshot or any(validation.get(key) != value for key, value in expected.items()):
            raise RuntimeError("Imported graph failed exact content/count readback validation")
        manifest["database_stopped_after_import"] = True
        manifest["validation"] = validation
        manifest["readback_snapshot_sha256"] = hashlib.sha256((output / "readback_snapshot.json").read_bytes()).hexdigest()
        current_step = "dump"
        _run_step([str(java), "-Xmx512m", "-cp", libraries, "org.neo4j.cli.AdminTool", "database", "dump", "neo4j", f"--to-path={output / 'dump'}"],
                  output, current_step, env, step_timeout)
        dump = output / "dump" / "neo4j.dump"
        if not dump.is_file() or not dump.stat().st_size:
            raise RuntimeError("Neo4j did not produce a nonempty database dump")
        manifest.update(status="complete", dump_path="dump/neo4j.dump", dump_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(), dump_bytes=dump.stat().st_size)
    except Exception as exc:
        manifest.update(status="error", failed_step=current_step, error_type=type(exc).__name__)
        _write_json(manifest_path, manifest)
        raise
    _write_json(manifest_path, manifest)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--neo4j-home", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--step-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = import_snapshot(args.snapshot, args.output_dir, neo4j_home=args.neo4j_home, java_home=args.java_home, step_timeout=args.step_timeout)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"error: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
