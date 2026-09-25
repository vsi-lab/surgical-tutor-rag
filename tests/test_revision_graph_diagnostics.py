import json
from pathlib import Path
import tempfile
import unittest

from backend.evaluation.revision.graph_diagnostics import (
    extraction_violations, quote_mismatch_kind, read_log, summarize, unique_calls,
)


def call(response_id="response-1", claims=None, cost=.01):
    payload = {"question": "Question?", "evidence": [{"chunk_id": "c1", "source": "source", "text": "manage- ment requires A."}]}
    return {"call_id": "call-1", "response_id": response_id, "status": "ok", "purpose": "relation_extraction",
            "request_sha256": "same-prompt", "request": {"messages": [{"role": "user", "content": json.dumps(payload)}]},
            "parsed": {"claims": claims or []}, "usage": {"cost": cost}}


def row(query_id="q1", condition="V_G", status="abstained", graph=True):
    value = {"query_id": query_id, "condition": condition, "question": "Question?", "status": status,
             "reason": "no_retained_evidence" if status != "error" else "Invalid quote",
             "initial_evidence": [{"chunk_id": "c1", "source": "source", "text": "manage- ment requires A."}]}
    if graph:
        value["graph_verification"] = {"retained_chunks": [], "chunk_reports": {"c1": {
            "reason": "insufficient_graph_coverage", "decisions": [{"state": "unknown", "reason": "unresolved_entity",
                "claim": {"source": "A", "target": "B"}, "resolution": {"source": {"status": "resolved"}, "target": {"status": "unresolved"}}}]}}}
    return value


class GraphDiagnosticsTests(unittest.TestCase):
    def test_shared_graph_traces_count_once_and_errors_are_not_abstentions(self):
        rows = [row(condition=arm) for arm in ["V_G", "V_GL"]] + [
            row(query_id="q2", condition=arm, status="error", graph=False) for arm in ["V_G", "V_GL"]]
        report = summarize(rows, [call()], {"query_ids": ["q1", "q2"], "conditions": ["V_G", "V_GL"]}, {"REQUIRES"})
        self.assertTrue(report["execution_records_complete"])
        self.assertFalse(report["all_requested_conditions_without_errors"])
        self.assertEqual(report["graph_trace_queries"], 1)
        self.assertEqual(report["shared_trace_double_counting_avoided"], 1)
        self.assertEqual(report["relation_states"], {"unknown": 1})
        self.assertEqual(report["conditions"]["V_G"]["error"], 1)
        self.assertEqual(report["conditions"]["V_G"]["abstained"], 1)
        self.assertIsNone(report["human_quality_metrics"])

    def test_distinct_traces_for_same_query_are_not_silently_merged(self):
        a, b = row(), row(condition="V_GL")
        b["graph_verification"]["chunk_reports"]["c1"]["reason"] = "empty_expected_relations"
        report = summarize([a, b], [], {"query_ids": ["q1"], "conditions": ["V_G", "V_GL"]}, set())
        self.assertEqual(report["unique_query_trace_pairs"], 2)
        self.assertEqual(report["queries_with_differing_graph_traces"], ["q1"])

    def test_copied_costs_deduplicate_but_separate_response_ids_do_not(self):
        first, retry = call(), call("response-2")
        unique, conflicts = unique_calls([first, first, retry])
        self.assertEqual(len(unique), 2)
        self.assertFalse(conflicts)
        report = summarize([row()], [first, first, retry], {"query_ids": ["q1"], "conditions": ["V_G"]}, set())
        self.assertEqual(report["api_usage"]["known_provider_cost_usd"], "0.02")
        self.assertEqual(report["api_usage"]["copied_records_removed"], 1)

    def test_payload_link_and_all_contract_violations_are_diagnostic_only(self):
        bad = {"chunk_id": "c1", "source": "management", "relation": "IMPROVES", "target": "A",
               "evidence_quote": "management requires A."}
        archived = call(claims=[bad])
        violations = extraction_violations(archived, {"REQUIRES"})
        self.assertEqual({x["kind"] for x in violations}, {"undeclared_predicate", "quote_mismatch"})
        report = summarize([row(status="error", graph=False)], [archived], {"query_ids": ["q1"], "conditions": ["V_G"]}, {"REQUIRES"})
        self.assertEqual(report["extraction"]["calls"][0]["query_ids"], ["q1"])
        self.assertEqual(report["extraction"]["quote_mismatch_classifications"], {"pdf_hyphenation_or_wrap_spacing": 1})
        self.assertEqual(report["conditions"]["V_G"]["error"], 1)
        self.assertEqual(report["conditions"]["V_G"]["abstained"], 0)

    def test_quote_patterns_and_incomplete_execution_are_explicit(self):
        self.assertIsNone(quote_mismatch_kind("exact", "an exact quote"))
        self.assertEqual(quote_mismatch_kind("two words", "two\nwords"), "whitespace_or_linebreak_variation")
        self.assertEqual(quote_mismatch_kind("A...B", "A then B"), "ellipsis_or_discontinuous_quote")
        report = summarize([row()], [], {"query_ids": ["q1", "q2"], "conditions": ["V_G"]}, set())
        self.assertFalse(report["execution_records_complete"])
        self.assertEqual(report["conditions"]["V_G"]["missing"], 1)
        self.assertIsNone(report["conditions"]["V_G"]["coverage"])

    def test_incomplete_final_line_is_reported_but_complete_bad_json_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "log.jsonl"
            path.write_bytes(b'{"ok":true}\n{"partial":')
            records, info = read_log(path)
            self.assertEqual(records, [{"ok": True}])
            self.assertTrue(info["incomplete_final_line_skipped"])
            path.write_bytes(b'{"ok":true}\n{"broken":\n')
            with self.assertRaises(ValueError):
                read_log(path)


if __name__ == "__main__":
    unittest.main()
