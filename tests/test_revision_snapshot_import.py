"""Fresh-directory and lossless-readback controls for offline snapshot imports."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend.evaluation.revision import import_snapshot as importer


def snapshot():
    return {
        "schema_version": 1, "provenance": "Synthetic test fixture, not clinical evidence",
        "nodes": [
            {"id": "external-a", "labels": ["Procedure"], "properties": {"name": "A", "sources": ["doc-a", "doc-b"], "nested": {"quote": "source phrase", "offsets": [1, 3]}, "empty": [], "none": None, "mixed": [1, "x"], "large": 2**80}},
            {"id": "external-b", "labels": ["Anatomy"], "properties": {"name": "B", "integer": 2, "decimal": 0.25, "boolean": True}},
        ],
        "edges": [{"id": "external-edge", "source": "external-a", "target": "external-b", "type": "INVOLVES", "properties": {"evidence_quote": "A involves B", "source": "fixture", "provenance": [{"page": 1, "span": [0, 12]}]}}],
    }


class SnapshotImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.source = self.workspace / "fixture.json"
        self.source.write_text(json.dumps(snapshot()), encoding="utf-8")
        self.distribution, self.jdk = self.workspace / "neo4j-2025.12.1", self.workspace / "jdk21"
        (self.distribution / "lib").mkdir(parents=True)
        (self.jdk / "bin").mkdir(parents=True)
        suffix = ".exe" if os.name == "nt" else ""
        for executable in ("java", "javac"):
            (self.jdk / "bin" / f"{executable}{suffix}").write_bytes(b"offline stub; never executed")

    def run_import(self, destination=None):
        return importer.import_snapshot(self.source, destination or self.workspace / "fresh", neo4j_home=self.distribution, java_home=self.jdk, workspace=self.workspace)

    @staticmethod
    def fake_step(command, output, name, env, timeout):
        if name == "import":
            raw = (output / "input_snapshot.json").read_bytes()
            expected = json.loads(raw)
            (output / "readback_snapshot.json").write_text(json.dumps(expected), encoding="utf-8")
            validation = {"status": "validated", "input_snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                "node_count": len(expected["nodes"]), "edge_count": len(expected["edges"]),
                "all_labels_endpoints_types_properties_match": True, "lossless_records_match": True,
                "database_shutdown_before_validation_output": True, "client_connectors_enabled": False}
            (output / "validation.json").write_text(json.dumps(validation), encoding="utf-8")
        elif name == "dump":
            (output / "dump" / "neo4j.dump").write_bytes(b"synthetic-dump-fixture")

    def test_nested_null_mixed_and_large_values_survive_validation(self):
        expected = snapshot()
        encoded = json.dumps(expected).encode()
        self.assertEqual(importer.read_snapshot(encoded), expected)
        self.assertEqual(importer.read_snapshot(b"\xef\xbb\xbf" + encoded), expected)

    def test_invalid_snapshot_fails_before_creating_directory_or_running_java(self):
        base = snapshot()
        malformed = []
        item = copy.deepcopy(base)
        item["nodes"][0]["properties"]["_revision_snapshot_id"] = "collision"
        malformed.append(item)
        item = copy.deepcopy(base)
        item["edges"][0]["target"] = "missing"
        malformed.append(item)
        item = copy.deepcopy(base)
        item["nodes"].append(copy.deepcopy(item["nodes"][0]))
        malformed.append(item)
        item = copy.deepcopy(base)
        item["nodes"][0]["labels"].append("Procedure")
        malformed.append(item)
        item = copy.deepcopy(base)
        item["edges"].append(copy.deepcopy(item["edges"][0]))
        malformed.append(item)
        for value in malformed:
            with self.subTest(value=value):
                self.source.write_text(json.dumps(value), encoding="utf-8")
                with patch.object(importer, "_run_step") as run:
                    with self.assertRaises(ValueError):
                        self.run_import()
                    run.assert_not_called()
                self.assertFalse((self.workspace / "fresh").exists())

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for raw in (b'{"nodes":[],"nodes":[],"edges":[]}', b'{"nodes":[],"edges":[],"value":NaN}', b'{"nodes":[],"edges":[],"value":1e999}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    importer.read_snapshot(raw)

    def test_existing_workspace_root_and_control_directories_are_refused(self):
        existing = self.workspace / "existing"
        existing.mkdir()
        (existing / "keep.txt").write_text("untouched", encoding="utf-8")
        for destination in (existing, self.workspace, self.workspace / ".git" / "data", self.workspace / ".codex" / "data", self.workspace.parent / "outside-workspace"):
            with self.subTest(destination=destination), patch.object(importer, "_run_step") as run:
                with self.assertRaises(ValueError):
                    self.run_import(destination)
                run.assert_not_called()
        self.assertEqual((existing / "keep.txt").read_text(), "untouched")

    def test_success_preserves_input_hash_and_validates_before_dump(self):
        original = self.source.read_bytes()
        with patch.object(importer, "_run_step", side_effect=self.fake_step) as run:
            result = self.run_import()
        output = self.workspace / "fresh"
        self.assertEqual([call.args[2] for call in run.call_args_list], ["compile", "import", "dump"])
        self.assertEqual((output / "input_snapshot.json").read_bytes(), original)
        self.assertEqual(result["input_snapshot_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["existing_instance_accessed"])
        self.assertTrue(result["database_stopped_after_import"])
        self.assertEqual(result["node_count"], 2)
        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(json.loads((output / "import_manifest.json").read_text()), result)
        self.assertIn("server.bolt.enabled=false", (output / "conf" / "neo4j.conf").read_text())
        self.assertNotIn("--overwrite-destination", " ".join(run.call_args_list[-1].args[0]))

    def test_bad_readback_blocks_dump_and_records_failure(self):
        def bad_readback(command, output, name, env, timeout):
            self.fake_step(command, output, name, env, timeout)
            if name == "import":
                recovered = snapshot()
                recovered["nodes"][0]["properties"]["nested"]["quote"] = "changed"
                (output / "readback_snapshot.json").write_text(json.dumps(recovered), encoding="utf-8")
        with patch.object(importer, "_run_step", side_effect=bad_readback) as run:
            with self.assertRaises(RuntimeError):
                self.run_import()
        self.assertEqual([call.args[2] for call in run.call_args_list], ["compile", "import"])
        report = json.loads((self.workspace / "fresh" / "import_manifest.json").read_text())
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["failed_step"], "import")

    def test_no_dump_or_timeout_never_claims_completion(self):
        for failure in ("no_dump", "timeout"):
            with self.subTest(failure=failure):
                destination = self.workspace / failure
                def fake(command, output, name, env, timeout):
                    if name == "dump":
                        if failure == "timeout":
                            raise subprocess.TimeoutExpired(command, timeout)
                        return
                    self.fake_step(command, output, name, env, timeout)
                with patch.object(importer, "_run_step", side_effect=fake):
                    with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                        self.run_import(destination)
                result = json.loads((destination / "import_manifest.json").read_text())
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["failed_step"], "dump")
                self.assertTrue((destination / "input_snapshot.json").exists())

    def test_generated_and_supplied_edge_ids_cannot_collide(self):
        value = snapshot()
        del value["edges"][0]["id"]
        second = copy.deepcopy(value["edges"][0])
        second["id"] = "_revision_missing_edge_0"
        value["edges"].append(second)
        with self.assertRaises(ValueError):
            importer.validate_snapshot(value)


if __name__ == "__main__":
    unittest.main()
