"""Offline experiment-integrity checks; no model, graph service, or network calls."""

import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.evaluation.revision import freeze_retrieval, run_matched
from backend.evaluation.revision.graph_verifier import FrozenGraph


class FakeClient:
    def __init__(self, overrides=None):
        self.calls = []
        self.overrides = overrides or {}

    def ask(self, system, payload, *, purpose, max_tokens):
        self.calls.append({"system": system, "payload": copy.deepcopy(payload), "purpose": purpose, "max_tokens": max_tokens})
        if purpose in self.overrides:
            supplied = self.overrides[purpose]
            if isinstance(supplied, Exception):
                raise supplied
            result = supplied(payload) if callable(supplied) else copy.deepcopy(supplied)
        elif purpose == "relation_extraction":
            result = {"claims": [
                {"chunk_id": item["chunk_id"], "source": "A", "relation": "PRECEDES", "target": "B",
                 "evidence_quote": item["text"], "required": True}
                for item in payload["evidence"]
            ]}
        elif purpose == "llm_verification":
            result = {"decision": "answer", "keep_chunk_ids": [item["chunk_id"] for item in payload["evidence"]], "reason": "Supported"}
        else:
            identifier = payload["evidence"][0]["chunk_id"]
            result = {"decision": "answer", "answer": f"A precedes B. [{identifier}]", "cited_chunk_ids": [identifier], "reason": "Evidence supports order"}
        return result, {"call_id": f"fake-{len(self.calls)}", "cache_hit": False, "usage": {"total_tokens": 1}}


def record():
    return {
        "query_id": "query-1", "question": "What happens first?", "split": "development",
        "legacy_answer": "HIDDEN_GOLD_ANSWER", "legacy_qrels": ["HIDDEN_QREL"],
        "answer": "ANOTHER_GOLD_ANSWER", "expected_answer": "EXPECTED_GOLD",
        "evidence": [
            {"chunk_id": "chunk-a", "source": "source-one", "text": "A occurs before B.", "score": 0.9, "gold_annotation": "HIDDEN_CHUNK_GOLD"},
            {"chunk_id": "chunk-b", "source": "source-two", "text": "A then B.", "score": 0.8},
        ],
    }


def graph(reverse=False):
    return FrozenGraph({
        "nodes": [{"id": name.lower(), "labels": ["Step"], "properties": {"name": name}} for name in ("A", "B")],
        "edges": [{"source": "b" if reverse else "a", "target": "a" if reverse else "b", "type": "PRECEDES", "properties": {"source_quote": "Graph provenance"}}],
    })


class RevisionRunnerTests(unittest.TestCase):
    def test_all_conditions_use_same_initial_evidence_and_standard_generation_prompt(self):
        client = FakeClient()
        rows = run_matched.run_query(record(), ["V", "V_L", "V_G", "V_GL"], client, graph())
        self.assertEqual([row["condition"] for row in rows], ["V", "V_L", "V_G", "V_GL"])
        self.assertEqual([row["status"] for row in rows], ["answered"] * 4)
        for row in rows:
            self.assertEqual(row["initial_evidence"], rows[0]["initial_evidence"])
            self.assertEqual(row["evidence"], rows[0]["evidence"])
        generator_calls = [call for call in client.calls if call["purpose"] == "answer_generation"]
        self.assertEqual(len(generator_calls), 4)
        for call in generator_calls:
            self.assertEqual(call["system"], run_matched.GENERATOR)
            self.assertEqual(call["payload"], generator_calls[0]["payload"])

    def test_gold_answers_and_qrels_never_enter_any_model_payload(self):
        client = FakeClient()
        run_matched.run_query(record(), ["V", "V_L", "V_G", "V_GL"], client, graph())
        serialized = json.dumps(client.calls)
        for forbidden in ("HIDDEN_GOLD_ANSWER", "HIDDEN_QREL", "ANOTHER_GOLD_ANSWER", "EXPECTED_GOLD", "HIDDEN_CHUNK_GOLD"):
            self.assertNotIn(forbidden, serialized)

    def test_combined_verifier_receives_graph_trace_but_standard_generator_does_not(self):
        client = FakeClient()
        run_matched.run_query(record(), ["V_L", "V_GL"], client, graph())
        calls = [call for call in client.calls if call["purpose"] == "llm_verification"]
        self.assertNotIn("graph_trace", calls[0]["payload"])
        self.assertIn("graph_trace", calls[1]["payload"])
        self.assertEqual(set(calls[1]["payload"]["graph_trace"]), {"chunk-a", "chunk-b"})
        for call in client.calls:
            if call["purpose"] == "answer_generation":
                self.assertNotIn("graph_trace", call["payload"])

    def test_llm_selection_unknown_duplicate_and_empty_answer_ids_are_errors(self):
        for identifiers in (["not-retrieved"], ["chunk-a", "chunk-a"], []):
            with self.subTest(identifiers=identifiers):
                client = FakeClient({"llm_verification": {"decision": "answer", "keep_chunk_ids": identifiers}})
                row = run_matched.run_query(record(), ["V_L"], client)[0]
                self.assertEqual(row["status"], "error")
                self.assertNotIn("answer_generation", [call["purpose"] for call in client.calls])

    def test_llm_filter_limits_evidence_seen_by_generator(self):
        client = FakeClient({"llm_verification": {"decision": "answer", "keep_chunk_ids": ["chunk-b"]}})
        row = run_matched.run_query(record(), ["V_L"], client)[0]
        self.assertEqual(row["status"], "answered")
        self.assertEqual([e["chunk_id"] for e in row["evidence"]], ["chunk-b"])
        self.assertEqual([e["chunk_id"] for e in client.calls[-1]["payload"]["evidence"]], ["chunk-b"])

    def test_llm_abstention_suppresses_generation(self):
        client = FakeClient({"llm_verification": {"decision": "abstain", "keep_chunk_ids": [], "reason": "Insufficient"}})
        row = run_matched.run_query(record(), ["V_L"], client)[0]
        self.assertEqual(row["status"], "abstained")
        self.assertEqual(row["answer"], "")
        self.assertEqual(len(client.calls), 1)

    def test_invalid_extraction_quote_is_error_not_an_abstention(self):
        claim = {"chunk_id": "chunk-a", "source": "A", "relation": "PRECEDES", "target": "B", "evidence_quote": "Invented quote"}
        client = FakeClient({"relation_extraction": {"claims": [claim]}})
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, graph())
        self.assertEqual([row["status"] for row in rows], ["error", "error"])
        self.assertEqual([call["purpose"] for call in client.calls], ["relation_extraction"])

    def test_unknown_extraction_predicate_or_chunk_is_error(self):
        base = {"chunk_id": "chunk-a", "source": "A", "relation": "PRECEDES", "target": "B", "evidence_quote": "A occurs before B."}
        for change in ({"relation": "UNDECLARED_PREDICATE"}, {"chunk_id": "unknown-id"}):
            with self.subTest(change=change):
                client = FakeClient({"relation_extraction": {"claims": [{**base, **change}]}})
                row = run_matched.run_query(record(), ["V_G"], client, graph())[0]
                self.assertEqual(row["status"], "error")
                self.assertEqual(len(client.calls), 1)

    def test_extraction_forces_required_true(self):
        result = {"claims": [{"chunk_id": "chunk-a", "source": "A", "relation": "PRECEDES", "target": "B", "evidence_quote": "A occurs before B.", "required": False}]}
        grouped, _ = run_matched.extract_relations(FakeClient({"relation_extraction": result}), record()["question"], record()["evidence"])
        self.assertTrue(grouped["chunk-a"][0]["required"])

    def test_empty_relations_or_graph_contradictions_block_before_generation(self):
        for frozen, overrides in [(graph(), {"relation_extraction": {"claims": []}}), (graph(reverse=True), {})]:
            with self.subTest(overrides=overrides):
                client = FakeClient(overrides)
                rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, frozen)
                self.assertEqual([row["status"] for row in rows], ["abstained", "abstained"])
                self.assertEqual([call["purpose"] for call in client.calls], ["relation_extraction"])
                self.assertTrue(all(not row["evidence"] for row in rows))

    def test_missing_graph_fails_closed_without_model_calls(self):
        client = FakeClient()
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client)
        self.assertEqual([row["status"] for row in rows], ["error", "error"])
        self.assertFalse(client.calls)

    def test_api_failures_are_errors_and_every_condition_keeps_a_record(self):
        failure = run_matched.ExperimentError("API request failed")
        client = FakeClient({purpose: failure for purpose in ("answer_generation", "llm_verification", "relation_extraction")})
        rows = run_matched.run_query(record(), ["V", "V_L", "V_G", "V_GL"], client, graph())
        self.assertEqual([row["status"] for row in rows], ["error"] * 4)
        for row in rows:
            self.assertEqual(row["query_id"], "query-1")
            self.assertEqual(row["human_evaluation_status"], "not_annotated")
            self.assertEqual(row["answer"], "")
            self.assertIn("reason", row)
            self.assertIn("model_calls", row)
            self.assertIn("latency_seconds", row)
            self.assertIn("usage", row)
            self.assertTrue(row["initial_evidence"])

    def test_generator_cannot_cite_unknown_evidence(self):
        client = FakeClient({"answer_generation": {"decision": "answer", "answer": "Claim [fabricated]", "cited_chunk_ids": ["fabricated"]}})
        self.assertEqual(run_matched.run_query(record(), ["V"], client)[0]["status"], "error")

    def test_empty_retrieval_abstains_without_generation(self):
        query = record()
        query["evidence"] = []
        client = FakeClient()
        rows = run_matched.run_query(query, ["V", "V_L"], client)
        self.assertEqual([row["status"] for row in rows], ["abstained", "abstained"])
        self.assertTrue(all(row["reason"] == "retrieval_empty" for row in rows))
        self.assertFalse(client.calls)

    def test_malformed_evidence_is_rejected_before_any_model_call(self):
        variants = []
        for replacement in ({"query_id": 1}, {"query_id": " "}, {"question": " "}, {"evidence": None}, {"evidence": {}}):
            variants.append({**record(), **replacement})
        missing = record()
        del missing["evidence"]
        variants.append(missing)
        for evidence in ([{"chunk_id": "x", "text": ""}], [{"chunk_id": "x", "text": "text", "score": float("nan")}], [{"chunk_id": "x", "text": "a"}, {"chunk_id": "x", "text": "b"}]):
            variants.append({**record(), "evidence": evidence})
        for query in variants:
            with self.subTest(query=query):
                client = FakeClient()
                with self.assertRaises(ValueError):
                    run_matched.run_query(query, ["V"], client)
                self.assertFalse(client.calls)

    def test_text_truncation_and_hash_are_archived_without_mutating_input(self):
        query = record()
        original = copy.deepcopy(query)
        client = FakeClient()
        row = run_matched.run_query(query, ["V"], client, max_chunk_chars=7)[0]
        self.assertEqual(query, original)
        for evidence in row["initial_evidence"]:
            self.assertEqual(len(evidence["text"]), 7)
            self.assertTrue(evidence["text_truncated"])
            self.assertEqual(len(evidence["original_text_sha256"]), 64)


class RevisionCallLoggingTests(unittest.TestCase):
    def test_provider_failure_is_archived_without_success_or_cache_entry(self):
        sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=TimeoutError("synthetic offline failure")))))
        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=Mock(return_value=sdk))}):
            client = run_matched.LoggedClient({"OPENAI_MODEL": "offline-model", "OPENAI_API_KEY": "unused-test-value"}, Path(directory), max_calls=2, cost_stop=1)
            with self.assertRaises(run_matched.ExperimentError) as raised:
                client.ask("System", {"evidence": []}, purpose="offline-test", max_tokens=10)
            archived = freeze_retrieval.read_jsonl(Path(directory) / "model_calls.jsonl")
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0]["status"], "error")
            self.assertFalse(client.cache)
            self.assertEqual(client.calls, 1)
            self.assertEqual(raised.exception.call_ref["call_id"], archived[0]["call_id"])

    def test_successful_requests_cache_and_budget_blocks_new_requests(self):
        response = SimpleNamespace(id="fake-response", model="offline-model", choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"decision":"abstain"}'))], usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 5, "cost": 0.01}))
        create = Mock(return_value=response)
        sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=Mock(return_value=sdk))}):
            client = run_matched.LoggedClient({"OPENAI_MODEL": "offline-model", "OPENAI_API_KEY": "unused-test-value"}, Path(directory), max_calls=1, cost_stop=1)
            first, meta_first = client.ask("System", {"question": "same"}, purpose="offline-test", max_tokens=10)
            cached, meta_cached = client.ask("System", {"question": "same"}, purpose="offline-test", max_tokens=10)
            self.assertEqual(first, cached)
            self.assertFalse(meta_first["cache_hit"])
            self.assertTrue(meta_cached["cache_hit"])
            self.assertEqual(create.call_count, 1)
            with self.assertRaises(run_matched.BudgetExceeded):
                client.ask("System", {"question": "different"}, purpose="offline-test", max_tokens=10)


class RevisionExtractionRepairTests(unittest.TestCase):
    @staticmethod
    def valid_claim():
        return {"chunk_id": "chunk-a", "source": "A", "relation": "PRECEDES", "target": "B",
                "evidence_quote": "A occurs before B.", "required": False}

    def test_validator_lists_all_errors_without_modifying_original(self):
        bad = {"claims": [{**self.valid_claim(), "relation": "INVENTED", "evidence_quote": "A before B"},
                          {**self.valid_claim(), "chunk_id": []}, {**self.valid_claim(), "source": ""}]}
        before = copy.deepcopy(bad)
        errors = run_matched.extraction_validation_errors(bad, record()["evidence"])
        self.assertEqual([e["code"] for e in errors], ["undeclared_predicate", "quote_not_in_evidence", "invalid_chunk_id", "malformed_claim_fields"])
        self.assertEqual(bad, before)
        for invalid in (None, [], {}, {"claims": {}}):
            self.assertEqual(run_matched.extraction_validation_errors(invalid, record()["evidence"])[0]["code"], "invalid_claims_schema")
        self.assertEqual(run_matched.extraction_validation_errors({"claims": []}, record()["evidence"]), [])

    def test_default_failure_keeps_original_call_reference_for_both_graph_arms(self):
        client = FakeClient({"relation_extraction": {"claims": [{**self.valid_claim(), "relation": "IMPROVES"}]}})
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, graph())
        self.assertEqual(len(client.calls), 1)
        for row in rows:
            self.assertEqual(row["status"], "error")
            self.assertEqual([call["call_id"] for call in row["model_calls"]], ["fake-1"])
            self.assertFalse(row["relation_extraction"]["repair_attempted"])
            self.assertEqual(row["relation_extraction"]["attempts"][0]["validation_errors"][0]["code"], "undeclared_predicate")

    def test_one_repair_is_graph_blind_preserves_original_and_is_shared(self):
        original = {"claims": [{**self.valid_claim(), "relation": "IMPROVES", "evidence_quote": "Not a quote"}]}
        repaired = {"claims": [self.valid_claim()]}
        client = FakeClient({"relation_extraction": original, "relation_extraction_repair": repaired})
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, graph(), extraction_retries=1)
        extraction = [call for call in client.calls if call["purpose"].startswith("relation_extraction")]
        self.assertEqual([call["purpose"] for call in extraction], ["relation_extraction", "relation_extraction_repair"])
        self.assertEqual(extraction[0]["system"], run_matched.RELATION_EXTRACTOR)
        self.assertEqual(extraction[1]["system"], run_matched.RELATION_REPAIR)
        payload = extraction[1]["payload"]
        self.assertEqual(set(payload), {"question", "evidence", "original_parsed_response", "validation_errors"})
        self.assertEqual(payload["question"], extraction[0]["payload"]["question"])
        self.assertEqual(payload["evidence"], extraction[0]["payload"]["evidence"])
        self.assertEqual(payload["original_parsed_response"], original)
        self.assertEqual([e["code"] for e in payload["validation_errors"]], ["undeclared_predicate", "quote_not_in_evidence"])
        serialized = json.dumps(extraction)
        for forbidden in ("Graph provenance", "HIDDEN_GOLD_ANSWER", "HIDDEN_QREL", "HIDDEN_CHUNK_GOLD"):
            self.assertNotIn(forbidden, serialized)
        for row in rows:
            self.assertEqual(row["status"], "answered")
            self.assertEqual([call["call_id"] for call in row["model_calls"][:2]], ["fake-1", "fake-2"])
            trace = row["relation_extraction"]
            self.assertEqual([a["contract_valid"] for a in trace["attempts"]], [False, True])
            self.assertTrue(trace["repair_attempted"])
        self.assertEqual(original["claims"][0]["relation"], "IMPROVES")
        self.assertFalse(repaired["claims"][0]["required"])

    def test_final_invalid_repair_stays_error_with_both_call_references(self):
        invalid = {"claims": [{**self.valid_claim(), "evidence_quote": "A  occurs before B."}]}
        client = FakeClient({"relation_extraction": invalid, "relation_extraction_repair": invalid})
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, graph(), extraction_retries=1)
        self.assertEqual(len(client.calls), 2)
        for row in rows:
            self.assertEqual(row["status"], "error")
            self.assertEqual(len(row["model_calls"]), 2)
            self.assertEqual([a["contract_valid"] for a in row["relation_extraction"]["attempts"]], [False, False])
            self.assertNotIn("graph_verification", row)

    def test_valid_first_response_never_triggers_repair(self):
        client = FakeClient()
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, graph(), extraction_retries=1)
        self.assertNotIn("relation_extraction_repair", [call["purpose"] for call in client.calls])
        self.assertTrue(all(not row["relation_extraction"]["repair_attempted"] for row in rows))

    def test_schema_repair_empty_claims_is_explicit_model_output_not_code_filtering(self):
        client = FakeClient({"relation_extraction": {"wrong_field": []}, "relation_extraction_repair": {"claims": []}})
        row = run_matched.run_query(record(), ["V_G"], client, graph(), extraction_retries=1)[0]
        self.assertEqual(row["status"], "abstained")
        self.assertTrue(row["relation_extraction"]["contract_valid"])
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(report["reason"] == "empty_expected_relations" for report in row["graph_verification"]["chunk_reports"].values()))

    def test_api_failure_is_not_repaired_and_archived_reference_is_retained(self):
        failure = run_matched.ExperimentError("API failure")
        failure.call_ref = {"call_id": "archived-failure", "cache_hit": False, "usage": {}}
        client = FakeClient({"relation_extraction": failure})
        rows = run_matched.run_query(record(), ["V_G", "V_GL"], client, graph(), extraction_retries=1)
        self.assertEqual(len(client.calls), 1)
        for row in rows:
            self.assertEqual(row["status"], "error")
            self.assertEqual(row["model_calls"][0]["call_id"], "archived-failure")
            self.assertFalse(row["relation_extraction"]["repair_attempted"])

    def test_bad_retry_limits_fail_before_calls(self):
        for limit in (-1, 2, True, 1.0):
            with self.subTest(limit=limit):
                client = FakeClient()
                with self.assertRaises(ValueError):
                    run_matched.run_query(record(), ["V_G"], client, graph(), extraction_retries=limit)
                self.assertFalse(client.calls)

    def test_extracting_required_claims_does_not_mutate_cached_parsed_result(self):
        parsed = {"claims": [self.valid_claim()]}
        client = SimpleNamespace(ask=lambda *args, **kwargs: (parsed, {"call_id": "cached", "cache_hit": True}))
        grouped, _ = run_matched.extract_relations(client, record()["question"], record()["evidence"])
        self.assertTrue(grouped["chunk-a"][0]["required"])
        self.assertFalse(parsed["claims"][0]["required"])


class RevisionFreezeTests(unittest.TestCase):
    def test_freezer_deduplicates_candidates_preserves_mapping_and_drops_gold(self):
        """Exercise the freeze boundary with deterministic fake vector/model modules."""
        vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        search = Mock(side_effect=[
            ([[1.0, 1.0, 0.0]] * 2 + [[1.0, 0.0, 0.0]], [[0, 1, 2], [1, 0, 2], [2, 0, 1]]),
            ([[0.9, 0.8, 0.7]], [[0, 1, 2]]),
        ])
        index = SimpleNamespace(ntotal=3, search=search, reconstruct=lambda row: vectors[row])
        numpy = SimpleNamespace(
            linspace=lambda start, end, count, dtype: SimpleNamespace(tolist=lambda: list(range(3))),
            dot=lambda left, right: sum(a * b for a, b in zip(left, right)),
            linalg=SimpleNamespace(norm=lambda values: math.sqrt(sum(value * value for value in values))),
        )
        model = SimpleNamespace(eval=Mock(), config=SimpleNamespace(_commit_hash="offline-model-commit"))
        modules = {
            "faiss": SimpleNamespace(read_index=Mock(return_value=index)),
            "numpy": numpy,
            "torch": SimpleNamespace(set_num_threads=Mock(), manual_seed=Mock()),
            "transformers": SimpleNamespace(AutoModel=SimpleNamespace(from_pretrained=Mock(return_value=model)), AutoTokenizer=SimpleNamespace(from_pretrained=Mock(return_value=object()))),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            long_identifier = "https://example.test/" + "guideline/" * 40 + "#chunk:1#sha256:" + "a" * 64
            corpus = [
                {"doc_id": long_identifier, "source": "source-a", "text": "A then B.", "faiss_indices": [0, 1]},
                {"doc_id": "other-canonical-id", "source": "source-b", "text": "Other evidence.", "faiss_indices": [2]},
            ]
            query = {"query_id": "q1", "question": "Question?", "legacy_answer": "HIDDEN_GOLD", "legacy_qrels": [long_identifier], "qrel_status": "resolved"}
            for path, rows in [(root / "corpus.jsonl", corpus), (root / "queries.jsonl", [query])]:
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            (root / "index.bin").write_bytes(b"offline-index-fixture")
            args = SimpleNamespace(corpus=root / "corpus.jsonl", queries=root / "queries.jsonl", index=root / "index.bin", output_dir=root / "outputs", model="offline-model", cpu_threads=1, seed=1, limit=0, top_k=2, allow_download=False)
            with patch.dict("sys.modules", modules), patch.object(freeze_retrieval, "embed", side_effect=[vectors, [[1.0, 0.0]]]), patch("builtins.print"):
                summary = freeze_retrieval.freeze(args)
            frozen = freeze_retrieval.read_jsonl(args.output_dir / "frozen_evidence.jsonl")[0]
            self.assertEqual(len(frozen["evidence"]), 2)
            self.assertEqual(len({item["chunk_id"] for item in frozen["evidence"]}), 2)
            self.assertTrue(all(len(item["chunk_id"]) < 32 for item in frozen["evidence"]))
            self.assertEqual(frozen["evidence"][0]["corpus_doc_id"], long_identifier)
            self.assertNotIn("HIDDEN_GOLD", json.dumps(frozen))
            self.assertNotIn("legacy_qrels", frozen)
            self.assertEqual(summary["diagnostic_hit_at_5"], 1.0)


if __name__ == "__main__":
    unittest.main()
