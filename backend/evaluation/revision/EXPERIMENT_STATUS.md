**Revision experiment status — 24 September 2026, America/Phoenix (25 September UTC)**

Work was performed directly on `main`, starting from commit `88df42a6ecb6591af70bcedf724123ad007d433c`. Code and reports are working-tree changes; no commit or push was made.

**Completed measured work**

The supplied Neo4j dump was successfully restored and exported without the original instance's password. It contains **49 nodes and 66 relationships**, whereas the submitted manuscript describes **434 entities and 389 relations**. It has no temporal or contraindication predicates and no recorded edge source references. The user reports that this is the only graph available to them and that the original may have been deleted; deletion is unconfirmed. Revision work therefore uses it as a separately frozen replacement snapshot, without claiming identity with the submission graph. [REPLACEMENT_STUDY_DRAFT.md](REPLACEMENT_STUDY_DRAFT.md) contains concrete disclosure and claim-change wording; [GRAPH_REVISION_GAPS.md](GRAPH_REVISION_GAPS.md) cites the manuscript/reviewer gaps.

The corrected data audit and dense retrieval cover all 60 legacy questions. The completed four-condition diagnostic run produced **240 query/condition records**, using the configured `openai/gpt-4o` model through OpenRouter. The 120 vector/LLM baseline records were reproduced through exact-request caching and verified to have identical inputs, decisions, evidence selections and answers. Every request, raw response, decision and token/cost record is saved. Original legacy results were not overwritten.

| Condition | Questions | Answered | Abstained | API/parsing errors | Answer coverage |
|---|---:|---:|---:|---:|---:|
| Vector RAG, V | 60 | 13 | 47 | 0 | 21.7% |
| Vector RAG + LLM verification, V_L | 60 | 10 | 50 | 0 | 16.7% |
| Vector RAG + graph verification, V_G | 60 | 0 | 50 | 10 | 0% |
| Vector RAG + graph + LLM verification, V_GL | 60 | 0 | 50 | 10 | 0% |

These are observed answering decisions, **not accuracy or hallucination results**. No human clinical labels have been supplied. A lower answer count does not establish greater reliability. The evaluation uses legacy, retrieval-selected questions, so it is a diagnostic experiment, not independent held-out validation and not a replacement for the paper's performance claims.

The two graph arms share each question's extraction and graph gate; their matching outcomes are not independent replications. No graph-retained evidence reached answer generation or the additional LLM verifier. The 10 graph errors per arm are extraction validation failures, not graph abstentions or clinical judgments. Raw API requests completed; extracted objects can still fail the declared predicate/quotation contract. The pilot exposed quotes that silently repaired PDF hyphenation, an ellipsis, and undeclared predicates. Quote mismatch alone does not establish clinical falsity. Failed records are preserved and were not selectively retried or converted into successful verification.

The [offline graph diagnostics](../revision_outputs/diagnostic60_graph_20260925/graph_diagnostics.json) explain the 50 non-error graph queries: 36 had no extracted relations and 14 had at least one. Among their 250 chunk occurrences, **232 had no extracted relations** and **18 failed graph coverage**. The checker evaluated 34 relations across those 18 chunks; **all 34 were unknown because at least one entity could not be resolved**. There were zero supported or contradicted relations. These counts deduplicate the shared V_G/V_GL traces; they do not measure clinical entailment or graph recall. The first reported validation error was a quote mismatch for three queries and an undeclared predicate for seven; a single extraction can contain multiple violations.

The run used the top five unique dense-retrieved chunks, capped at 2,400 characters each in both conditions. This truncated 261 of the 300 starting chunk occurrences per condition. That fixed evidence budget is part of the experimental setting and can omit later supporting text; these counts must not be described as results using all available guideline text. Ten questions were answered by both conditions, three only by V, and 47 by neither.

The completed matched run contains **190 unique archived model requests**: 70 generation, 60 LLM verification and 60 relation extraction. All completed with provider finish reason `stop`; there were no API failures. Provider-reported cost is **$1.463510**, comprising the previous $0.950955 baseline cost and **$0.512555 additional graph-extraction cost**. The separate connectivity request cost $0.000045, giving **$1.463555 total reported model cost**. The 190 calls consumed 519,232 prompt and 16,543 completion tokens. All include a cost field. Reused baseline and pilot logs must not be added again when totaling spending.

**Replacement-study development follow-up**

After inspecting those failures, a separate development run applied a declared single correction attempt to each malformed parsed extraction. The correction sees only the original question/evidence, parsed extraction and deterministic validation errors; it receives no graph content or graph feedback. Exact quotations and allowed predicates remain required. Original and correction calls, failures and hashes are preserved; the original run remains intact.

The [development run](../revision_outputs/development_repair_20260925/run_summary.json) contains another 240 condition records with 120 baseline records reproduced exactly through caching. Ten queries triggered one correction each; five corrections passed the extraction contract and five still failed (four quotation errors, one undeclared predicate). **Both graph arms answered 0/60, abstained on 55/60, and failed on 5/60.** All 43 relations that reached the checker were unknown because of unresolved entities. Reducing schema failures did not restore useful answer coverage or demonstrate clinical improvement.

This is a development comparison on already inspected legacy questions, not an independent confirmatory experiment. The ten added provider calls cost **$0.1222375**, bringing unique matched/development calls to 200 and their reported cost to **$1.5857475**; including the earlier connectivity check, total reported model cost is **$1.5857925**. See [development_analysis.json](../revision_outputs/development_repair_20260925/development_analysis.json) for per-query correction outcomes and preserved input hashes.

An offline search of the 1,486 corpus items found endpoint co-occurrence candidates for **52/66 edges**, yielding 100 exact excerpts from up to three different source documents per edge. Fourteen edges had no lexical candidate within the fixed 600-character endpoint span. The [source review sheet](../revision_outputs/source_candidates_20260925/source_candidates_for_review.csv) has 114 rows, including unmatched-edge placeholders; all human labels are blank. Co-occurrence does not establish relation entailment, recover historical citations, or prove an unmatched edge false. This is a starting point for source review, and the graph was not modified. See [source_candidates.json](../revision_outputs/source_candidates_20260925/source_candidates.json) for offsets, hashes and search rules.

A bounded recovery search found no additional graph export in tracked Git objects, two unreachable historical commits, the professor package, or the other `revision_request.zip` and `revision_v1.zip` archives. This does not establish permanent deletion or rule out backups outside the inspected scope. The existing importer drops additional node/edge properties and does not propagate its source filename; its normal predicate mapping lacks temporal/contraindication edges. Those implementation findings are consistent with the observed missing provenance but do not establish the dump's historical identity.

**Data and retrieval findings**

- The original index contains 2,228 rows from 18 sources, but only 1,486 distinct source/chunk/text evidence items. There are 742 exact repeated rows.
- Source plus local chunk number is not sufficient either: 70 source/chunk pairs contain different texts. Stable evidence identifiers now include a text fingerprint, with reversible short IDs for model prompts.
- All 33 questions in the legacy verification subset also appear in the 60-question benchmark.
- Only 34/60 legacy evidence addresses resolve consistently; 26 require fresh relevance assessment. Resolving an address does not establish that the evidence is clinically relevant.
- The sampled BioClinicalBERT/index alignment control passed. The vector run retrieves a legacy-labeled relevant chunk in the first five unique chunks for **1/34** resolvable questions. Diagnostic MRR over deduplicated evidence is **0.0254783540**. These are measurements against problematic old labels, not a clean estimate of the system's true retrieval quality.

**Implemented and checked**

- Corrected retrieval metrics: stable source/chunk/text identity, deduplication before rank/cutoff, bounded AP, explicit MAP/MRR cutoffs, and errors for invalid/missing relevance labels.
- A reproducible evidence freezer with sampled encoder/index alignment checking.
- A matched experiment runner with the same initial evidence and standard generator across conditions; the generator may abstain in every condition. The LLM verifier filters evidence before generation. All four conditions have now been run using the supplied graph snapshot.
- A symbolic three-state verifier with explicit unknown/contradicted distinction, direction checking, empty-relation handling and graph-conflict vetoes. Its pilot defaults require full extracted-relation support and coverage. Graph relation induction is LLM-assisted; this is not a wholly non-LLM graph condition.
- Blinded response-annotation export, graph triple sampling, and aggregation that leaves missing human metrics undefined. No simulated graph improvement or automatic substitute for human labels is used.
- Isolated dump restore/export with preserved input hashes and logs, plus graph inventory and a blank review queue covering all 66 stored edges. A second independent restore reproduced all node labels/properties and typed relationships/properties; fresh database UUIDs differ.
- Optional one-attempt extraction-contract correction with complete attempt logging, plus deterministic source-candidate search that preserves verbatim excerpts and leaves all human judgments blank.
- **110 offline tests passed** after extraction correction and source-candidate integration. Tests validate code behavior, not clinical effectiveness.

**Review files ready now**

The completed four-condition run is in [diagnostic60_graph_20260925](../revision_outputs/diagnostic60_graph_20260925/):

- [run_summary.json](../revision_outputs/diagnostic60_graph_20260925/run_summary.json) and [responses.jsonl](../revision_outputs/diagnostic60_graph_20260925/responses.jsonl): all 240 measured records, including errors.
- [reviewer_1.csv](../revision_outputs/diagnostic60_graph_20260925/reviewer_1.csv) and [reviewer_2.csv](../revision_outputs/diagnostic60_graph_20260925/reviewer_2.csv): blank independent review sheets for the same 23 answered baseline responses. No graph answers exist to rate; the graph arms' answer-error risk is undefined, not zero.
- [annotation_status.json](../revision_outputs/diagnostic60_graph_20260925/annotation_status.json): all expected records are present, but human annotation is incomplete. `matched_run_complete` describes record presence, not successful execution of every case or completed clinical evaluation.
- `model_calls.jsonl`, `run_manifest.json` and `source_snapshot/`: complete request log and exact frozen inputs/implementation used.
- [graph_diagnostics.json](../revision_outputs/diagnostic60_graph_20260925/graph_diagnostics.json): deduplicated graph traces, unresolved entity mentions, linked extraction errors and quotation mismatch examples. Its heuristics describe failures without changing the original acceptance rule.

The earlier baseline-only run remains preserved in [diagnostic60_v_vl_20260924](<C:/projects/jon market analysis/surgical tutor rag/backend/evaluation/revision_outputs/diagnostic60_v_vl_20260924>):

- [run_summary.json](<C:/projects/jon market analysis/surgical tutor rag/backend/evaluation/revision_outputs/diagnostic60_v_vl_20260924/run_summary.json>): measured operational counts and cost.
- [responses.jsonl](<C:/projects/jon market analysis/surgical tutor rag/backend/evaluation/revision_outputs/diagnostic60_v_vl_20260924/responses.jsonl>): 120 raw system records.
- [reviewer_1.csv](<C:/projects/jon market analysis/surgical tutor rag/backend/evaluation/revision_outputs/diagnostic60_v_vl_20260924/reviewer_1.csv>) and [reviewer_2.csv](<C:/projects/jon market analysis/surgical tutor rag/backend/evaluation/revision_outputs/diagnostic60_v_vl_20260924/reviewer_2.csv>): 23 answered-response rows for independent blinded human review. All rating fields are blank.
- [annotation_status.json](<C:/projects/jon market analysis/surgical tutor rag/backend/evaluation/revision_outputs/diagnostic60_v_vl_20260924/annotation_status.json>): explicitly reports incomplete annotations and the missing graph condition. Clinical error risk is undefined.
- `model_calls.jsonl`, `run_manifest.json`, and `source_snapshot/`: raw model interactions, frozen configuration/checksums and the exact runner source used for the completed run. Later runner hardening preserves the already completed evidence rather than rewriting its provenance.

Keep the private mapping and raw system labels away from annotators. The annotation sheets require source-guideline access, a qualified review rubric, independent ratings and documented adjudication; reading only retrieved snippets cannot establish that an answer omits no important clinical information. See [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md).

The inputs and diagnostic results are under `backend/evaluation/revision_outputs/data_audit/` and `backend/evaluation/revision_outputs/retrieval_20260924/`. Generated raw outputs are kept locally and ignored by Git; preserve them with the research records.

**Graph recovered; study identity and provenance unresolved**

The previous cloud Neo4j address does not resolve, and the running local instance rejects the credentials in `backend/.env`. The application URI was set to `neo4j://127.0.0.1:7687`; its password was not reset. These credentials are no longer a blocker for offline revision experiments because the supplied dump restored successfully into a separate workspace directory. The original Desktop instance was not modified.

The [snapshot](../revision_outputs/dump_restore_20260925/graph_snapshot.json), [inventory](../revision_outputs/dump_restore_20260925/graph_inventory.md) and [66-edge review queue](../revision_outputs/dump_restore_20260925/graph_triples_for_review.csv) are available. Dump SHA-256: `c131de1649c761e2b5528b5470b3380f8cea0ab1f69d9d4b4287c669e67a802e`. [DUMP_RESTORE.md](DUMP_RESTORE.md) records reproduction steps. The graph has six predicate types, none encoding the manuscript's temporal/contraindication checks. Its timestamps and five `confidence` values are not source citations or human validation.

**Highest-impact next work**

1. Agree on a transparent replacement-study scope using the available 49/66 snapshot. Disclose that the original graph is unavailable for verification and remove original graph-dependent claims unless their supporting records can be recovered. Do not transfer the old performance tables to the replacement graph.
2. Have qualified reviewers use the prepared source-candidate and 66-edge review sheets to establish actual source support, direction and normalization. Obtain full source guidelines for context. This creates new validation records rather than reconstructing historical curation by assumption.
3. Build or curate a versioned graph only from justified source material, or narrow the paper to the current diagnostic findings. Freeze development choices before a new independent evaluation; do not add edges or aliases merely to fit inspected evaluation questions.
4. Obtain independent questions/relevance judgments and real human answer labels, then run the fixed comparison on the versioned replacement graph. The current 0-answer graph results cannot support a useful-answer reliability advantage.

**Remaining research inputs**

The original graph-validation labels, 25-case surgeon ratings, and an independently authored/unfiltered question set remain unprovided. The current code prepares genuine annotation work but cannot create observations on behalf of clinical reviewers. Final clinical error rates, graph precision/coverage validation, and held-out comparative claims depend on those records or new qualified annotation.

Reproducible commands, condition definitions, execution limits and caveats are in [README.md](README.md). The graph-format contract is in [GRAPH_VERIFIER_FORMAT.md](GRAPH_VERIFIER_FORMAT.md).
