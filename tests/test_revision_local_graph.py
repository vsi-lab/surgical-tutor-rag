import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.evaluation.revision import local_graph


class LocalGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.outputs = self.root / "backend/evaluation/revision_outputs"
        self.home = self.outputs / "fixture"
        self.home.mkdir(parents=True)

    def test_only_completed_marked_imports_can_be_served(self):
        with patch.object(local_graph, "OUTPUTS", self.outputs):
            with self.assertRaisesRegex(ValueError, "isolated"):
                local_graph.validate_home(self.home)
            (self.home / ".revision-snapshot-import").write_text("fixture")
            manifest = self.home / "import_manifest.json"
            manifest.write_text(json.dumps({"status": "error"}))
            with self.assertRaisesRegex(ValueError, "complete"):
                local_graph.validate_home(self.home)
            manifest.write_text(json.dumps({"status": "complete"}))
            self.assertEqual(local_graph.validate_home(self.home)[0], self.home.resolve())
            with self.assertRaisesRegex(ValueError, "isolated"):
                local_graph.validate_home(self.root)

    def test_env_change_preserves_other_settings_and_previous_connection(self):
        from dotenv import dotenv_values
        env = self.root / "backend/.env"
        env.write_text("NEO4J_URI=bolt://old:7687\nNEO4J_USER=olduser\nNEO4J_PASSWORD=old-test-secret\nOTHER_SETTING=untouched\n")
        credentials = {"uri": "bolt://127.0.0.1:7688", "password": "new-test-secret"}
        with patch.object(local_graph, "WORKSPACE", self.root):
            local_graph.configure_env(credentials, self.home)
            local_graph.configure_env(credentials, self.home)
        values = dotenv_values(env)
        self.assertEqual(values["OTHER_SETTING"], "untouched")
        self.assertEqual(values["NEO4J_URI"], credentials["uri"])
        self.assertEqual(values["NEO4J_PASSWORD"], credentials["password"])
        prior = json.loads((self.home / "previous_backend_neo4j.private.json").read_text())
        self.assertEqual(prior["NEO4J_PASSWORD"], "old-test-secret")
        self.assertEqual(set(prior), {"NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"})


if __name__ == "__main__":
    unittest.main()
