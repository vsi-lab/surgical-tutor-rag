"""Start/stop an isolated rebuilt Neo4j database over authenticated loopback Bolt.

Credentials stay in the ignored output directory and optionally backend/.env.
No Desktop instance is configured, reset, overwritten, or registered.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

WORKSPACE = Path(__file__).resolve().parents[3]
OUTPUTS = WORKSPACE / "backend/evaluation/revision_outputs"


def validate_home(path):
    home = Path(path).resolve(strict=True)
    if OUTPUTS not in home.parents or not (home / ".revision-snapshot-import").is_file():
        raise ValueError("Expected an isolated imported database inside revision_outputs")
    manifest = json.loads((home / "import_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Import and dump validation must be complete before serving")
    return home, manifest


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def check_connection(credentials):
    from neo4j import GraphDatabase
    with GraphDatabase.driver(credentials["uri"], auth=("neo4j", credentials["password"]), connection_timeout=5) as driver:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            edges = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
    return {"nodes": nodes, "relationships": edges}


def configure_env(credentials, home):
    from dotenv import dotenv_values, set_key
    env_file = WORKSPACE / "backend/.env"
    if not env_file.is_file():
        raise ValueError("Expected existing backend/.env; no other settings file will be edited")
    backup = home / "previous_backend_neo4j.private.json"
    if not backup.exists():
        previous = dotenv_values(env_file)
        with backup.open("x", encoding="utf-8") as handle:
            json.dump({key: previous.get(key) for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")}, handle)
    set_key(env_file, "NEO4J_URI", credentials["uri"])
    set_key(env_file, "NEO4J_USER", "neo4j")
    set_key(env_file, "NEO4J_PASSWORD", credentials["password"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("start", "stop", "status"))
    p.add_argument("--home", type=Path, required=True)
    p.add_argument("--port", type=int, default=7688)
    p.add_argument("--neo4j-home", type=Path, default=Path.home() / ".Neo4jDesktop2/Cache/dbmss/neo4j-enterprise-2025.12.1")
    p.add_argument("--java-home", type=Path, default=Path.home() / ".Neo4jDesktop2/Cache/runtime/zulu21.44.17-ca-jdk21.0.8-win_x64")
    p.add_argument("--configure-env", action="store_true")
    args = p.parse_args()
    home, manifest = validate_home(args.home)
    private = home / "connection.private.json"
    credentials = json.loads(private.read_text(encoding="utf-8")) if private.exists() else None
    if args.action == "stop":
        (home / "run/STOP.request").write_text("Stop requested by local_graph helper.\n", encoding="utf-8")
        print("Graceful stop requested for this isolated graph.")
        return
    if args.action == "status":
        if not credentials or not port_open(credentials["port"]):
            print(json.dumps({"running": False}))
        else:
            print(json.dumps({"running": True, "uri": credentials["uri"], **check_connection(credentials)}))
        return
    if not 1024 <= args.port <= 65535:
        p.error("Choose an unprivileged local port")
    if credentials and credentials["port"] != args.port:
        p.error("Port differs from the saved connection; use the existing port")
    if port_open(args.port):
        p.error("Port is occupied; inspect status or choose a different unused port")
    if not credentials:
        credentials = {"uri": f"bolt://127.0.0.1:{args.port}", "port": args.port,
                       "user": "neo4j", "password": secrets.token_urlsafe(32)}
        with private.open("x", encoding="utf-8") as handle:
            json.dump(credentials, handle)
    classes = home / "server_classes"
    classes.mkdir(exist_ok=True)
    java = args.java_home / "bin/java.exe"
    javac = args.java_home / "bin/javac.exe"
    libraries = str(args.neo4j_home / "lib/*")
    with (home / "server_compile.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(javac), "-cp", libraries, "-d", str(classes), str(Path(__file__).with_name("LocalGraphServer.java"))],
                       stdout=log, stderr=log, check=True, timeout=90)
    command = [str(java), "-Xmx512m", "--add-opens=java.base/java.nio=ALL-UNNAMED",
               "--add-opens=java.base/java.lang=ALL-UNNAMED", "-cp", str(classes) + os.pathsep + libraries,
               "LocalGraphServer", str(home)]
    with (home / "server_stdout.log").open("a", encoding="utf-8") as out, (home / "server_stderr.log").open("a", encoding="utf-8") as err:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
            start_new_session=os.name != "nt", close_fds=True)
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Local graph exited; see server_stderr.log")
        status_file = home / "server_status.json"
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text(encoding="utf-8"))
                if status.get("state") == "running" and status.get("pid") == process.pid:
                    counts = check_connection(credentials)
                    expected = manifest["validation"]
                    if counts != {"nodes": expected["node_count"], "relationships": expected["edge_count"]}:
                        raise RuntimeError("Live graph counts do not match validated import")
                    if args.configure_env:
                        configure_env(credentials, home)
                    print(json.dumps({"running": True, "uri": credentials["uri"], "pid": process.pid,
                                      "backend_env_updated": args.configure_env, **counts}))
                    return
            except json.JSONDecodeError:
                pass
        time.sleep(0.5)
    (home / "run/STOP.request").write_text("Startup deadline exceeded.\n", encoding="utf-8")
    raise TimeoutError("Server readiness timeout; graceful stop requested")


if __name__ == "__main__":
    main()
