"""Restore an author-supplied Neo4j dump into a fresh workspace copy and export JSON.

Uses a matching local Neo4j Enterprise distribution and JDK. Does not connect to,
stop, configure, or overwrite an existing Neo4j Desktop instance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def run_step(command, output_dir, name, env=None):
    with (output_dir / f"{name}_stdout.txt").open("w", encoding="utf-8") as out, \
         (output_dir / f"{name}_stderr.txt").open("w", encoding="utf-8") as err:
        result = subprocess.run(command, stdout=out, stderr=err, env=env, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{name} exited {result.returncode}; inspect saved logs in {output_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--neo4j-home", type=Path, required=True, help="Installed matching distribution containing lib/")
    parser.add_argument("--java-home", type=Path, required=True, help="Compatible JDK containing java and javac")
    parser.add_argument("--output-dir", type=Path, required=True, help="New, nonexistent directory inside this workspace")
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[3]
    output = args.output_dir.resolve()
    dump = args.dump.resolve(strict=True)
    distribution = args.neo4j_home.resolve(strict=True)
    jdk = args.java_home.resolve(strict=True)
    suffix = ".exe" if os.name == "nt" else ""
    java, javac = jdk / "bin" / f"java{suffix}", jdk / "bin" / f"javac{suffix}"
    if output == workspace or workspace not in output.parents:
        parser.error("Output must be a fresh subdirectory inside the repository workspace")
    if output.exists():
        parser.error("Output already exists; choose a new directory (no overwrites or removals)")
    if not dump.is_file() or not java.is_file() or not javac.is_file() or not (distribution / "lib").is_dir():
        parser.error("Dump, JDK executables, or Neo4j library directory not found")
    output.mkdir(parents=True)
    for name in ("conf", "data", "logs", "run", "import", "exporter_classes"):
        (output / name).mkdir()
    (output / ".revision-dump-copy").write_text("Isolated author-supplied dump copy for revision diagnostics.\n", encoding="utf-8")
    (output / "conf" / "neo4j.conf").write_text(
        "server.memory.heap.initial_size=256m\nserver.memory.heap.max_size=512m\n"
        "server.memory.pagecache.size=128m\n", encoding="utf-8")
    shutil.copyfile(dump, output / "import" / "neo4j.dump")
    libs = str(distribution / "lib" / "*")
    env = dict(os.environ, JAVA_HOME=str(jdk), NEO4J_HOME=str(output), NEO4J_CONF=str(output / "conf"))
    run_step([str(java), "-Xmx512m", "-cp", libs, "org.neo4j.cli.AdminTool", "database", "load",
              f"--from-path={output / 'import'}", "neo4j"], output, "load", env)
    source = Path(__file__).with_name("DumpGraphExport.java")
    classes = output / "exporter_classes"
    run_step([str(javac), "-cp", libs, "-d", str(classes), str(source)], output, "compile")
    run_step([str(java), "-Xmx512m", "--add-opens=java.base/java.nio=ALL-UNNAMED",
              "--add-opens=java.base/java.lang=ALL-UNNAMED", "-cp", str(classes) + os.pathsep + libs,
              "DumpGraphExport", str(output), str(output / "graph_snapshot.json"), str(dump)], output, "export")
    snapshot = json.loads((output / "graph_snapshot.json").read_text(encoding="utf-8"))
    manifest = {"dump_name": dump.name, "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                "neo4j_distribution": distribution.name, "jdk": jdk.name,
                "exporter_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "node_count": len(snapshot["nodes"]), "edge_count": len(snapshot["edges"]),
                "original_instance_accessed": False, "submission_graph_identity_confirmed": False}
    (output / "restore_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
