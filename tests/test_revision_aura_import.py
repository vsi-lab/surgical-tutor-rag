import json
from pathlib import Path
import tempfile
import unittest

from backend.evaluation.revision import aura_import


class AuraImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def credential_file(self, **changes):
        values = {
            "NEO4J_URI": "neo4j+s://fixture.databases.neo4j.io",
            "NEO4J_USERNAME": "fixture-user",
            "NEO4J_PASSWORD": "fixture-secret",
            "NEO4J_DATABASE": "fixture-db",
            "AURA_INSTANCEID": "fixture",
            "AURA_INSTANCENAME": "Fixture",
            **changes,
        }
        path = self.root / "credentials.txt"
        path.write_text("\n".join(f'{key}="{value}"' for key, value in values.items()) + "\n")
        return path

    def test_credentials_are_loaded_without_becoming_safe_metadata(self):
        result = aura_import.load_aura_credentials(self.credential_file())
        self.assertEqual(result["host"], "fixture.databases.neo4j.io")
        self.assertEqual(result["user"], "fixture-user")
        self.assertEqual(result["password"], "fixture-secret")
        safe_keys = {"instance_id", "instance_name", "host", "database", "credential_file_name"}
        self.assertNotIn("fixture-secret", json.dumps({key: result[key] for key in safe_keys}))

    def test_missing_duplicate_or_unencrypted_credentials_fail(self):
        missing = self.credential_file(NEO4J_PASSWORD="")
        with self.assertRaisesRegex(ValueError, "missing"):
            aura_import.load_aura_credentials(missing)
        duplicate = self.credential_file()
        duplicate.write_text(duplicate.read_text() + 'NEO4J_USERNAME="again"\n')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            aura_import.load_aura_credentials(duplicate)
        with self.assertRaisesRegex(ValueError, "encrypted"):
            aura_import.load_aura_credentials(self.credential_file(NEO4J_URI="bolt://localhost:7687"))

    def test_property_mapping_matches_lossless_import_policy(self):
        record = {"id": "n1", "labels": ["Procedure"], "properties": {
            "name": "appendectomy", "valid": False, "sources": ["a", "b"],
            "empty": [], "nested": {"a": 1}, "mixed": [1, "two"]}}
        mapped = aura_import.mapped_properties(record, "n1", 3)
        self.assertEqual(mapped["sources"], ["a", "b"])
        self.assertEqual(mapped["empty"], "[]")
        self.assertEqual(json.loads(mapped["nested"]), {"a": 1})
        self.assertEqual(json.loads(mapped["mixed"]), [1, "two"])
        self.assertEqual(mapped["_revision_json_encoded_keys"], ["empty", "nested", "mixed"])
        self.assertEqual(json.loads(mapped["_revision_record_json"]), record)

    def test_snapshot_tokens_and_prepared_endpoints_are_explicit(self):
        snapshot = {"nodes": [
            {"id": "p", "labels": ["Procedure"], "properties": {"name": "appendectomy"}},
            {"id": "a", "labels": ["Anatomy"], "properties": {"name": "appendix"}},
        ], "edges": [{"id": "e", "source": "p", "target": "a", "type": "INVOLVES", "properties": {}}]}
        nodes, edges = aura_import.prepared_records(snapshot)
        self.assertEqual([node["labels"] for node in nodes], [("Procedure",), ("Anatomy",)])
        self.assertEqual((edges[0]["source"], edges[0]["target"], edges[0]["type"]), ("p", "a", "INVOLVES"))
        for bad in ("bad label", "x` MATCH (n)", "", "3Label"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                aura_import.safe_token(bad)

    def test_backend_env_backup_and_change_are_limited_to_neo4j(self):
        from dotenv import dotenv_values
        workspace = self.root / "workspace"
        output = workspace / "backend/evaluation/revision_outputs/aura-run"
        (workspace / "backend").mkdir(parents=True)
        output.mkdir(parents=True)
        env = workspace / "backend/.env"
        env.write_text("NEO4J_URI=bolt://old\nNEO4J_USER=old\nNEO4J_PASSWORD=old-secret\nOTHER=keep\n")
        credentials = {"uri": "neo4j+s://fixture.databases.neo4j.io", "user": "new", "password": "new-secret"}
        aura_import.configure_backend_env(credentials, output, workspace)
        current = dotenv_values(env)
        self.assertEqual(current["OTHER"], "keep")
        self.assertEqual(current["NEO4J_USER"], "new")
        previous = json.loads((output / "previous_backend_neo4j.private.json").read_text())
        self.assertEqual(previous["NEO4J_PASSWORD"], "old-secret")

    def test_backend_env_backup_refuses_nonignored_output(self):
        workspace = self.root / "workspace"
        output = workspace / "public-output"
        (workspace / "backend").mkdir(parents=True)
        output.mkdir()
        (workspace / "backend/.env").write_text(
            "NEO4J_URI=bolt://old\nNEO4J_USER=old\nNEO4J_PASSWORD=old-secret\n")
        credentials = {"uri": "neo4j+s://fixture.databases.neo4j.io", "user": "new", "password": "new-secret"}
        with self.assertRaisesRegex(ValueError, "Git-ignored revision_outputs"):
            aura_import.configure_backend_env(credentials, output, workspace)
        self.assertFalse((output / "previous_backend_neo4j.private.json").exists())


if __name__ == "__main__":
    unittest.main()
