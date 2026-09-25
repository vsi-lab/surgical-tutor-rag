# Revision experiments and human evaluation

This directory contains an auditable revision workflow: inspect legacy data, freeze dense retrieval, run matched verification conditions, and export genuine human annotation work. New code and new pilot runs do **not** retroactively validate the original manuscript's retrieval, hallucination, graph-quality or surgeon-rating results. Missing measurements remain missing.

Run commands from the repository root with a Python environment containing the relevant dependencies. `data_audit` needs NumPy; `freeze_retrieval` also needs FAISS, PyTorch and Transformers; `preflight` needs python-dotenv, Neo4j and optionally the OpenAI client; `run_matched` needs python-dotenv and the OpenAI client. The offline graph verifier, annotation tools and their focused tests use the standard library. Use the repository's configured environment; the full application requirements include additional components not needed by this workflow.

## 1. Audit the legacy corpus and questions

```powershell
python -m backend.evaluation.revision.data_audit --output-dir backend/evaluation/revision_outputs/data_audit
```

This reads the repository's existing trusted `backend/faiss_index.index.meta.npy` and the 60/33-question legacy files. It writes:

- `corpus_manifest.jsonl`: source/chunk/text identities, exact text hashes and all corresponding FAISS rows; identical repeated evidence is deduplicated.
- `legacy_queries.jsonl`: question identities, dataset overlap, address-resolution findings and original selection metadata.
- `annotation_candidates.jsonl`: a blank relevance-assessment queue, without treating legacy answers as new ground truth.
- `audit_summary.json`: counts and input/output checksums.

The output is **legacy diagnostic data**, not an independently held-out benchmark. Address resolution checks whether an old label identifies a chunk; it does not prove clinical relevance. New human labeling of previously retrieval-selected questions does not remove that selection bias. Confirmatory evaluation requires a separately prespecified, unfiltered question set, independent relevance judgments and a development/test split frozen before evaluation outputs are inspected.

## 2. Freeze actual dense retrieval

```powershell
python -m backend.evaluation.revision.freeze_retrieval --corpus backend/evaluation/revision_outputs/data_audit/corpus_manifest.jsonl --queries backend/evaluation/revision_outputs/data_audit/legacy_queries.jsonl --index backend/faiss_index.index --output-dir backend/evaluation/revision_outputs/retrieval_20260924 --top-k 5
```

The default encoder is `emilyalsentzer/Bio_ClinicalBERT`, with attention-mask mean pooling, 512-token truncation and normalized vectors. Model files must already be cached unless `--allow-download` is supplied. The script checks encoder/index alignment on sampled corpus rows and stops if that control fails. This control does not establish alignment for every row or establish retrieval relevance.

Outputs are `retrieval_manifest.json`, `frozen_evidence.jsonl` and `retrieval_summary.json`. The summary's legacy hit/rank statistics are diagnostics over resolvable old labels; unresolved labels are not converted into irrelevant judgments. Retrieval is dense-only: no graph reranking is silently added. Each frozen question has stable chunk IDs, text, source, similarity and FAISS-row provenance.

The current freezer labels its provenance as legacy diagnostic. Do not relabel these outputs as held-out results. A future confirmatory input must preserve independently frozen dataset, relevance and split provenance and update the preparation manifest to describe that actual process.

## 3. Check configured services and export a graph

Set `OPENAI_API_KEY`, `OPENAI_MODEL` and, when needed, `OPENAI_BASE_URL` through environment variables or the local untracked `backend/.env`. Graph export reads `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD`. Environment values override the file. Keep credentials out of experiment files and command arguments.

```powershell
python -m backend.evaluation.revision.preflight --env-file backend/.env --output-dir backend/evaluation/revision_outputs/preflight_20260924 --check-model
```

The graph operation is read-only and writes `graph_snapshot.json` when successful. `preflight.json` records availability and graph counts/checksum. `--check-model` makes one short, billable connectivity request; omit it for graph-only checking. An optional `--graph-uri` changes the database endpoint for this command without editing the application's configuration. A current database export still needs author confirmation that it corresponds to the submitted graph.

A failed connection is not a graph experiment. Graph conditions require an actual snapshot using the format in [GRAPH_VERIFIER_FORMAT.md](GRAPH_VERIFIER_FORMAT.md); an author-provided compatible export may be used instead. Graph-quality judgments require source passages and human review, beyond successful database access.

A Neo4j database dump is also sufficient without the original instance's password. [DUMP_RESTORE.md](DUMP_RESTORE.md) documents the isolated restoration/export used for the supplied dump. `export_dump` requires a matching local Neo4j Enterprise distribution and compatible JDK, creates a fresh directory inside this repository, and refuses overwrites. It does not access the existing Desktop instance.

```powershell
python -m backend.evaluation.revision.graph_inventory --graph backend/evaluation/revision_outputs/dump_restore_20260925/graph_snapshot.json --output backend/evaluation/revision_outputs/dump_restore_20260925/inventory_new.json --markdown backend/evaluation/revision_outputs/dump_restore_20260925/inventory_new.md
```

Inventory reports structural counts, missing relation families, name ambiguities, provenance-field availability and graph conflicts. Absence of a conflict in a graph with no relevant edges is not successful validation.

## 4. Run a bounded matched pilot

The core comparison has three conditions (`V`, `V_L`, `V_G`); the combined graph-plus-LLM arm (`V_GL`) is an optional extension. This core pilot example assumes the graph snapshot exists:

```powershell
python -m backend.evaluation.revision.run_matched --evidence backend/evaluation/revision_outputs/retrieval_20260924/frozen_evidence.jsonl --graph backend/evaluation/revision_outputs/preflight_20260924/graph_snapshot.json --env-file backend/.env --conditions V,V_L,V_G --limit 3 --workers 2 --max-calls 30 --cost-stop 1.0 --output-dir backend/evaluation/revision_outputs/matched_core_pilot_20260924
```

| Condition | Operation after the same initial dense retrieval |
|---|---|
| `V` | Generate from the initial evidence, with permission to abstain. |
| `V_L` | LLM verification selects evidence or abstains; the shared generator answers from retained evidence. |
| `V_G` | LLM-assisted relation extraction supplies explicit claims to the symbolic graph verifier; the shared generator answers from graph-retained evidence. |
| `V_GL` (optional) | Apply the graph stage, then LLM verification with graph traces, then the shared generator. |

All conditions share the question, initial evidence, generator prompt/model/settings and generator abstention capability. Verification can filter evidence, so final generator inputs can differ. The default `--max-chunk-chars 2400` truncates each initial chunk consistently across conditions; original text hashes and truncation flags are recorded. Generator budgets match, while verification adds model calls and token use. This is not a match on total computation.

`V_G` includes an LLM extractor; it is not a wholly non-LLM comparison. Quote containment is checked, but it does not prove that the extracted relation follows from that quote. Entity mapping, predicate direction, graph incompleteness and extraction errors remain possible. The extractor deliberately avoids inventing omitted contraindications or treating a mere list as procedural order; consequently, graph consistency cannot establish completeness or detect every critical omission.

`--extraction-retries 1` optionally permits one graph-blind re-extraction after a parsed response violates the extraction contract. The default is `0`. The correction receives the original evidence/response and deterministic validation errors, never the graph or its verification results. Both attempts and validation errors remain in the logs; failed corrections stay errors. API/JSON-parse failures are not retried by this option. The policy and correction-prompt hash are recorded in the manifest. Use a new output directory, label changes selected after inspecting failures as development work, and do not overwrite the original run. A successful schema correction does not prove semantic or clinical correctness.

Graph support and known-relation coverage default conservatively to `1.0` (`--min-support`, `--min-coverage`). Empty expectations cannot certify a chunk; missing edges are unknown; explicit contradictions and graph conflicts follow the documented veto rules. Any relaxed thresholds require development-only justification. These are support measures, not calibrated clinical probabilities. Passing the evidence check does not establish answer correctness or safety.

Without a graph, an interim run can use `--conditions V,V_L` and omit `--graph`. It does not complete the core graph comparison. The current artifact directory for that comparison is `backend/evaluation/revision_outputs/pilot_v_vl_20260924`; a full legacy diagnostic run can be invoked as follows:

```powershell
python -m backend.evaluation.revision.run_matched --evidence backend/evaluation/revision_outputs/retrieval_20260924/frozen_evidence.jsonl --env-file backend/.env --conditions V,V_L --limit 0 --workers 2 --max-calls 240 --cost-stop 1.0 --output-dir backend/evaluation/revision_outputs/new_diagnostic60_v_vl
```

`--limit 0` selects all frozen questions. Choose a new output directory whenever changing the query set or conditions. To include the optional combined arm, use `--conditions V,V_L,V_G,V_GL` in a new graph-enabled run and declare all four conditions during annotation export.

`--max-calls` caps newly reserved model requests, including prior logged calls on resume. `--cost-stop` stops starting requests when completed, provider-reported dollar cost reaches the threshold; in-flight calls can still finish and exceed that amount. If the provider omits cost, `calls_without_cost` flags the missing information and the reported total is incomplete. This is not a guaranteed dollar spending cap. The connectivity request is separate from the matched-run budget.

## 5. Inspect the preserved run, then annotate

Each run directory contains:

- `run_manifest.json`: evidence/graph/code/prompt hashes, query IDs, conditions, model, thresholds and generation settings.
- `responses.jsonl`: one record per completed question/condition, including question, initial and retained evidence, answer or abstention/error status, verification traces, timing and model-call references.
- `model_calls.jsonl`: requests, raw responses, parse results, provider identity, usage and failures. Exact matching requests may be cached and shared; use this log for total usage, rather than summing repeated response references.
- `run_summary.json`: operational status counts and coverage; clinical quality metrics remain pending human labels.

API, budget, parsing and infrastructure failures are `error`, separate from intentional `abstained` decisions. They are not safe answers. Existing response rows, including errors, are treated as completed on resume; only absent question/condition rows are scheduled. A changed frozen configuration requires a new directory. If failed cases need rerunning, preserve the original run and record the retry policy and linkage explicitly. Cache sharing and concurrent calls mean observed latency is not a controlled timing benchmark.

For graph runs, `python -m backend.evaluation.revision.graph_diagnostics --run-dir RUN_DIRECTORY` produces offline diagnostics of chunk rejections, unresolved entities and extraction-contract failures. It deduplicates graph traces shared by `V_G` and `V_GL`, links extraction calls through the exact question/evidence payload, and never changes failed records into abstentions. Quotation mismatch heuristics are diagnostic descriptions, not repaired model outputs or clinical labels.

```powershell
python -m backend.evaluation.revision.annotations export --input backend/evaluation/revision_outputs/pilot_v_vl_20260924/responses.jsonl --output backend/evaluation/revision_outputs/pilot_v_vl_20260924/blinded.csv --mapping backend/evaluation/revision_outputs/pilot_v_vl_20260924/private_mapping.json --seed 2026 --expected-conditions V,V_L,V_G
```

The interim `V,V_L` export intentionally declares the planned core set, so absence of `V_G` stays visible as an incomplete comparison. For the core graph run, replace the run directory in these commands. Follow [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md): two qualified independent human reviewers, real source material, preserved original ratings, and a final adjudicated sheet. The export leaves every clinical label blank. Keep the mapping and unblinded run separate from reviewers. Neutral chunk IDs are retained to resolve answer citations. Once humans supply final labels:

```powershell
python -m backend.evaluation.revision.annotations report --input backend/evaluation/revision_outputs/pilot_v_vl_20260924/responses.jsonl --mapping backend/evaluation/revision_outputs/pilot_v_vl_20260924/private_mapping.json --annotations backend/evaluation/revision_outputs/pilot_v_vl_20260924/adjudicated.csv --output backend/evaluation/revision_outputs/pilot_v_vl_20260924/annotation_report.json
```

Reports keep development/test splits separate. Coverage uses all eligible questions, retaining infrastructure failures in its denominator. Answer-risk uses genuinely assessed answered responses; missing labels leave the main metric undefined. Unsupported claims, procedural errors and critical omissions may overlap. Human claim-count faithfulness is independent of hallucination labeling. Descriptive Wilson intervals are not paired superiority tests. The report uses the declared expected conditions stored in the private mapping and flags partial comparisons as incomplete; reconcile all question IDs with the frozen run/dataset manifest as well.

To prepare graph review separately:

```powershell
python -m backend.evaluation.revision.graph_audit --graph backend/evaluation/revision_outputs/preflight_20260924/graph_snapshot.json --output backend/evaluation/revision_outputs/graph_triples.csv --manifest backend/evaluation/revision_outputs/graph_sample_manifest.json --per-relation 25 --seed 2026
```

This produces a relation-stratified sample with blank human labels, not a graph-quality score. Source-statement and task-coverage assessment is a separate requirement; an edge sample alone cannot establish recall.

For an available graph without source citations, this offline helper finds literal endpoint co-occurrences in the frozen corpus for human inspection:

```powershell
python -m backend.evaluation.revision.graph_source_candidates --graph backend/evaluation/revision_outputs/dump_restore_20260925/graph_snapshot.json --corpus backend/evaluation/revision_outputs/data_audit/corpus_manifest.jsonl --output-dir backend/evaluation/revision_outputs/new_source_candidates
```

It preserves exact excerpts, offsets and hashes, includes unmatched edges, leaves rating fields blank and does not modify the graph. A candidate passage is not recovered historical provenance or validation; absence of a lexical match is not proof of a false relation. Check full source context and record actual qualified review before using citations or quality claims.

## Validation and reporting limits

```powershell
python -m unittest discover -s tests -p "test_revision_*.py" -v
```

Tests check software behavior using fixtures. They do not substitute for clinical measurements. Preserve raw outputs, independently judged relevance, graph provenance, original human annotations, development choices and any failures before reporting manuscript results. Do not manufacture missing denominators, infer human ratings from model scores, or claim that a pilot completes the original paper's requested revision.
