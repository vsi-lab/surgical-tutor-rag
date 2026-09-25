"""Read-only graph snapshot and bounded model connectivity check. Never emit secrets."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse


def load_settings(env_file: str | Path) -> dict[str, str]:
    from dotenv import dotenv_values
    settings = {key: str(value) for key, value in dotenv_values(env_file).items() if value is not None}
    for key in settings.keys() | {"OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_API_KEY", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"}:
        if key in os.environ:
            settings[key] = os.environ[key]
    return settings


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def safe_error(exc: Exception) -> dict:
    # Exception strings can contain request URLs, auth headers or provider diagnostics.
    message = str(exc).lower()
    category = ("dns_resolution_failed" if "resolve address" in message or "getaddrinfo" in message else
                "authentication_failed" if "unauthorized" in message or "authentication" in message else
                "connection_failed")
    return {"error_type": type(exc).__name__, "category": category,
            "http_status": getattr(exc, "status_code", None)}


def export_graph(settings: dict, output: Path) -> dict:
    from neo4j import GraphDatabase, READ_ACCESS
    logging.getLogger("neo4j").setLevel(logging.CRITICAL)
    uri = settings.get("NEO4J_URI", "")
    if not all(settings.get(k) for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")):
        return {"status": "missing_configuration"}
    driver = GraphDatabase.driver(uri, auth=(settings["NEO4J_USER"], settings["NEO4J_PASSWORD"]),
                                  connection_timeout=10, connection_acquisition_timeout=15,
                                  max_transaction_retry_time=0)
    try:
        def read_snapshot(tx):
            nodes = [dict(row) for row in tx.run(
                "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties ORDER BY id")]
            edges = [dict(row) for row in tx.run(
                "MATCH (s)-[r]->(t) RETURN elementId(r) AS id, elementId(s) AS source, "
                "elementId(t) AS target, type(r) AS type, properties(r) AS properties ORDER BY id")]
            return nodes, edges
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes, edges = session.execute_read(read_snapshot)
        snapshot = {"schema_version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
                    "provenance": "read-only export of configured database; submission-time identity unconfirmed",
                    "nodes": nodes, "edges": edges}
        save_json(output, snapshot)
        return {"status": "available" if nodes else "empty_graph", "node_count": len(nodes),
                "edge_count": len(edges), "relation_types": dict(Counter(e["type"] for e in edges)),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "snapshot_path": str(output)}
    except Exception as exc:
        return {"status": "unavailable", **safe_error(exc)}
    finally:
        driver.close()


def check_model(settings: dict) -> dict:
    from openai import OpenAI
    key = settings.get("OPENAI_API_KEY")
    model = settings.get("OPENAI_MODEL")
    if not key or not model:
        return {"status": "missing_configuration"}
    try:
        with OpenAI(api_key=key, base_url=settings.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                    timeout=30, max_retries=0) as client:
            response = client.chat.completions.create(model=model, temperature=0, max_tokens=16,
                messages=[{"role": "user", "content": "Connectivity check. Reply only READY."}])
        return {"status": "available", "requested_model": model, "returned_model": response.model,
                "response_id": response.id, "usage": response.usage.model_dump() if response.usage else None,
                "returned_text": response.choices[0].message.content}
    except Exception as exc:
        return {"status": "unavailable", "requested_model": model, **safe_error(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--graph-uri", help="Override endpoint without changing the application's .env")
    parser.add_argument("--check-model", action="store_true", help="Make one 16-output-token connectivity request")
    args = parser.parse_args()
    settings = load_settings(args.env_file)
    if args.graph_uri:
        settings["NEO4J_URI"] = args.graph_uri
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "provider_host": urlparse(settings.get("OPENAI_BASE_URL", "")).hostname,
              "model": settings.get("OPENAI_MODEL"),
              "graph": export_graph(settings, args.output_dir / "graph_snapshot.json")}
    if args.check_model:
        report["model_check"] = check_model(settings)
    save_json(args.output_dir / "preflight.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
