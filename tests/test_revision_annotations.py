"""Clinical annotations must remain human, blinded, and denominator-explicit."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.evaluation.revision.annotations import (
    CONDITIONS,
    CSV_FIELDS,
    ERROR_FIELDS,
    build_report,
    export_annotations,
    load_run,
    main,
    wilson_interval,
)


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run = self.base / "run.jsonl"
        self.sheet = self.base / "blinded.csv"
        self.mapping = self.base / "private.json"
        self.records = [
            {
                "query_id": f"q{number}", "question": f"Synthetic test question {number}?",
                "condition": condition, "split": "test", "status": status,
                "answer": "Synthetic answer." if status == "answered" else "",
                "evidence": [{"chunk_id": "private-id", "source": "synthetic-source", "text": "Synthetic supporting text.", "score": 0.91}],
                "reason": "private-trace", "latency_seconds": 0.1, "usage": {"tokens": 20},
            }
            for number, status in enumerate(("answered", "answered", "abstained", "error"), 1)
            for condition in CONDITIONS
        ]
        self.write_run()

    def write_run(self):
        self.run.write_text("".join(json.dumps(row) + "\n" for row in self.records), encoding="utf-8")

    def export(self):
        export_annotations(self.run, self.sheet, self.mapping, seed=123, expected_conditions=CONDITIONS)
        with self.sheet.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def write_sheet(self, rows):
        with self.sheet.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def label_all(self):
        rows = self.export()
        ids = {item["annotation_id"]: item for item in json.loads(self.mapping.read_text())["items"]}
        for row in rows:
            first = ids[row["annotation_id"]]["query_id"] == "q1"
            row.update({"annotator_id": "human-adjudicator", "unsupported_claim": "0", "procedural_error": "1" if first else "0", "critical_omission": "1" if first else "0", "correct": "0" if first else "1", "supported_claims": "2", "total_claims": "2"})
        self.write_sheet(rows)
        return rows

    def test_export_blinds_condition_and_keeps_clinical_labels_blank(self):
        rows = self.export()
        self.assertEqual(len(rows), 8)
        self.assertEqual(set(rows[0]), set(CSV_FIELDS))
        self.assertEqual(len({row["annotation_id"] for row in rows}), 8)
        for row in rows:
            self.assertTrue(row["annotation_id"].startswith("a_"))
            self.assertEqual(row["annotator_id"], "")
            for field in (*ERROR_FIELDS, "correct", "supported_claims", "total_claims"):
                self.assertEqual(row[field], "")
            self.assertEqual(json.loads(row["evidence"])[0]["chunk_id"], "private-id")
            self.assertNotIn("score", row["evidence"])
            self.assertNotIn("private-trace", json.dumps(row))
        other_sheet, other_map = self.base / "other.csv", self.base / "other.json"
        export_annotations(self.run, other_sheet, other_map, seed=123, expected_conditions=CONDITIONS)
        self.assertEqual(self.sheet.read_bytes(), other_sheet.read_bytes())
        self.assertEqual(self.mapping.read_bytes(), other_map.read_bytes())

    def test_blank_annotations_are_unknown_not_no_error(self):
        self.export()
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertTrue(report["matched_run_complete"])
        self.assertFalse(report["annotations_complete"])
        self.assertFalse(report["complete_for_primary_descriptive_reporting"])
        condition = report["splits"]["test"]["V"]
        self.assertIsNone(condition["hallucination_risk_among_answered"]["value"])
        self.assertIsNone(condition["hallucination_risk_among_answered"]["numerator"])
        self.assertEqual(condition["answered_missing_error_labels"], 2)
        self.assertEqual(condition["coverage"]["value"], 0.5)
        self.assertEqual(condition["infrastructure_failure_rate"]["value"], 0.25)

    def test_truthful_denominators_overlapping_errors_and_distinct_faithfulness(self):
        self.label_all()
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertTrue(report["annotations_complete"])
        self.assertTrue(report["complete_for_primary_descriptive_reporting"])
        condition = report["splits"]["test"]["V"]
        self.assertEqual(condition["eligible_queries"], 4)
        self.assertEqual(condition["answered"], 2)
        self.assertEqual(condition["abstained"], 1)
        self.assertEqual(condition["infrastructure_errors"], 1)
        self.assertEqual(condition["hallucination_risk_among_answered"]["numerator"], 1)
        self.assertEqual(condition["hallucination_risk_among_answered"]["denominator"], 2)
        self.assertEqual(condition["hallucination_risk_among_answered"]["value"], 0.5)
        self.assertEqual(condition["error_categories"]["procedural_error"]["among_all_answered"]["numerator"], 1)
        self.assertEqual(condition["error_categories"]["critical_omission"]["among_all_answered"]["numerator"], 1)
        # Complete factual support does not erase a procedural error or omission.
        self.assertEqual(condition["faithfulness"]["micro_average_all_answered"], 1.0)

    def test_deleted_rating_row_makes_report_incomplete(self):
        rows = self.label_all()
        removed = rows.pop()
        self.write_sheet(rows)
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertEqual(report["missing_annotation_ids"], [removed["annotation_id"]])
        self.assertFalse(report["complete_for_primary_descriptive_reporting"])

    def test_partial_rating_never_becomes_complete_safe_answer(self):
        rows = self.label_all()
        rows[0]["critical_omission"] = ""
        self.write_sheet(rows)
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertFalse(report["annotations_complete"])
        self.assertFalse(report["complete_for_primary_descriptive_reporting"])
        self.assertTrue(any(value["hallucination_risk_among_answered"]["value"] is None for value in report["splits"]["test"].values()))

    def test_invalid_duplicate_unknown_or_unattributed_labels_rejected(self):
        rows = self.label_all()
        original = [dict(row) for row in rows]
        cases = [
            ("duplicate", lambda: original + [dict(original[0])]),
            ("unknown", lambda: [{**original[0], "annotation_id": "unknown"}, *original[1:]]),
            ("nonbinary", lambda: [{**original[0], "correct": "yes"}, *original[1:]]),
            ("no human", lambda: [{**original[0], "annotator_id": ""}, *original[1:]]),
            ("invalid counts", lambda: [{**original[0], "supported_claims": "3"}, *original[1:]]),
            ("half counts", lambda: [{**original[0], "supported_claims": ""}, *original[1:]]),
            ("changed answer", lambda: [{**original[0], "answer": "Edited response"}, *original[1:]]),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                self.write_sheet(mutate())
                with self.assertRaises(ValueError):
                    build_report(self.run, self.mapping, self.sheet)

    def test_frozen_run_mutation_and_incomplete_mapping_rejected(self):
        self.export()
        self.records[0]["answer"] = "Changed after annotation export"
        self.write_run()
        with self.assertRaisesRegex(ValueError, "digest"):
            build_report(self.run, self.mapping, self.sheet)
        self.records[0]["answer"] = "Synthetic answer."
        self.write_run()
        mapping = json.loads(self.mapping.read_text())
        mapping["items"].pop()
        self.mapping.write_text(json.dumps(mapping))
        with self.assertRaisesRegex(ValueError, "every answered"):
            build_report(self.run, self.mapping, self.sheet)

    def test_missing_condition_is_explicit_and_not_complete_matched_run(self):
        self.records = [row for row in self.records if row["condition"] != "V_GL"]
        self.write_run()
        self.label_all()
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertFalse(report["matched_run_complete"])
        self.assertFalse(report["complete_for_primary_descriptive_reporting"])
        missing = report["splits"]["test"]["V_GL"]
        self.assertEqual(missing["missing_records"], 4)
        self.assertIsNone(missing["coverage"]["value"])

    def test_default_core_comparison_flags_missing_graph_without_requiring_optional_combined(self):
        self.records = [row for row in self.records if row["condition"] in ("V", "V_L")]
        self.write_run()
        export_annotations(self.run, self.sheet, self.mapping, seed=123)
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertEqual(report["expected_conditions"], ["V", "V_L", "V_G"])
        self.assertEqual(set(report["splits"]["test"]), {"V", "V_L", "V_G"})
        self.assertEqual(report["splits"]["test"]["V_G"]["missing_records"], 4)
        self.assertFalse(report["matched_run_complete"])

    def test_four_arm_run_requires_explicit_four_arm_declaration(self):
        with self.assertRaisesRegex(ValueError, "outside the declared"):
            export_annotations(self.run, self.sheet, self.mapping)
        for conditions in ([], ["V", "V"], ["V", "imaginary"], "V,V_L"):
            with self.subTest(conditions=conditions), self.assertRaises(ValueError):
                export_annotations(self.run, self.sheet, self.mapping, expected_conditions=conditions)

    def test_neutral_citation_ids_survive_blinding(self):
        for row in self.records:
            if row["status"] == "answered":
                row["answer"] = "Synthetic supported answer [c-123]."
                row["evidence"][0]["chunk_id"] = "c-123"
        self.write_run()
        rows = self.export()
        for row in rows:
            evidence = json.loads(row["evidence"])
            self.assertIn("[c-123]", row["answer"])
            self.assertEqual(evidence[0]["chunk_id"], "c-123")
            self.assertEqual(evidence[0]["label"], "E1")
            self.assertNotIn("condition", row)

    def test_cli_persists_declared_expected_conditions(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()):
            status = main(["export", "--input", str(self.run), "--output", str(self.sheet), "--mapping", str(self.mapping), "--expected-conditions", "V,V_L,V_G,V_GL"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(self.mapping.read_text())["expected_conditions"], list(CONDITIONS))

    def test_dev_and_test_never_pooled(self):
        for row in self.records:
            if row["query_id"] == "q2":
                row["split"] = "development"
        self.write_run()
        self.label_all()
        report = build_report(self.run, self.mapping, self.sheet)
        self.assertEqual(set(report["splits"]), {"development", "test"})
        self.assertEqual(report["splits"]["development"]["V"]["eligible_queries"], 1)
        self.assertEqual(report["splits"]["test"]["V"]["eligible_queries"], 3)

    def test_invalid_run_rows_rejected(self):
        original = [dict(row) for row in self.records]
        for name, records in [
            ("duplicate", original + [original[0]]),
            ("invalid status", [{**original[0], "status": "success"}, *original[1:]]),
            ("empty answer", [{**original[0], "answer": ""}, *original[1:]]),
            ("missing question", [{**original[0], "question": ""}, *original[1:]]),
            ("split leak", [{**original[0], "split": "development"}, *original[1:]]),
        ]:
            with self.subTest(name=name):
                self.records = records
                self.write_run()
                with self.assertRaises(ValueError):
                    load_run(self.run)

    def test_zero_answer_and_zero_claim_denominators_are_undefined(self):
        self.records = [row for row in self.records if row["status"] != "answered"]
        self.write_run()
        self.export()
        report = build_report(self.run, self.mapping, self.sheet)
        condition = report["splits"]["test"]["V"]
        self.assertEqual(condition["coverage"]["value"], 0)
        self.assertIsNone(condition["hallucination_risk_among_answered"]["value"])
        self.assertIsNone(condition["hallucination_risk_among_answered"]["wilson_95_ci"])
        self.assertIsNone(condition["faithfulness"]["micro_average_all_answered"])

    def test_no_overwrite_of_annotation_work_and_cli_path_guard(self):
        self.export()
        with self.assertRaisesRegex(ValueError, "already exist"):
            export_annotations(self.run, self.sheet, self.mapping)
        with self.assertRaises(SystemExit) as exc:
            main(["report", "--input", str(self.run), "--mapping", str(self.mapping), "--annotations", str(self.sheet), "--output", str(self.sheet)])
        self.assertEqual(exc.exception.code, 2)

    def test_wilson_intervals_are_bounded_and_not_false_certainty(self):
        self.assertIsNone(wilson_interval(0, 0))
        low, high = wilson_interval(0, 10)
        self.assertGreaterEqual(low, 0)
        self.assertGreater(high, 0.27)
        low, high = wilson_interval(10, 10)
        self.assertLess(low, 0.73)
        self.assertLessEqual(high, 1)


if __name__ == "__main__":
    unittest.main()
