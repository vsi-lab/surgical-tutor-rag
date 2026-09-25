# Transparent replacement study: candidate manuscript and response text

**DRAFT for author review.** This file proposes wording and an editing checklist. It does not edit the submitted manuscript, record author approval, establish completed human review, or send any message. Statements about proposed changes must become descriptions of completed work only after those changes are actually made. New development results must be added from their own frozen artifacts when available.

## Study identity and scope

The only graph currently available to this revision workflow contains **49 nodes and 66 relations**. The submitted manuscript describes 434 entities and 389 relations. The originally described graph is **not currently available for verification**. Its deletion has not been established, and the available dump must not be described as the original study graph.

The defensible replacement is to designate this existing author-supplied graph as a **newly frozen revision-study snapshot** and evaluate it transparently. This does not mean it was newly constructed, reproduces the original graph, or validates the old graph-dependent results. Keep the original submitted files and diagnostic runs as historical records; do not attach the new graph to old result tables as if they were generated together. The detailed source comparison is in [GRAPH_REVISION_GAPS.md](GRAPH_REVISION_GAPS.md).

## Candidate manuscript wording

### Methods: study provenance and knowledge graph

> During revision, the graph described in the original submission was not available for verification. The available author-supplied Neo4j dump contains 49 nodes and 66 directed typed relations, differing from the 434 entities and 389 relations described in that submission. We therefore treat this available artifact as a separate graph snapshot for revision-stage development and diagnostic evaluation. Its use does not reproduce or validate the original graph-dependent results. We cannot establish that the originally described graph was deleted.
>
> The snapshot contains INVOLVES (13), MAY_CAUSE (17), REQUIRES (6), REQUIRES_MEDICATION (6), SHOWS_INSTRUMENT (5), and USES_TECHNIQUE (19) relations. It contains no PRECEDES/FOLLOWS or contraindication relations. Consequently, procedural-order and contraindication verification are not demonstrated capabilities of the evaluated snapshot. The export does not retain edge-level guideline citations, and human source-grounding and graph-quality labels have not been supplied. These limitations preclude describing this snapshot as a clinically validated or fully guideline-traceable graph.

### Methods: completed diagnostic comparison

> We performed a diagnostic comparison using the 60 existing legacy questions. Because these questions were previously selected with reference to retrieval performance, this evaluation is not an independent held-out test. Each condition received the same initial top-five unique dense-retrieved chunks, with a fixed cap of 2,400 characters per chunk. The generator and its option to abstain were shared across conditions. Verification could remove evidence before generation.
>
> The graph condition used LLM-assisted extraction of explicit relations followed by deterministic graph checking. It was therefore not a wholly non-LLM comparator. Absent relations were treated as unknown rather than false, and the diagnostic graph gate required both extracted-relation support and known-relation coverage of 1.0. Those settings define this diagnostic run; they are not evidence of calibration or optimal thresholds. Extraction contract failures were recorded separately from intentional abstention. Subsequent extractor changes are development work and require separately versioned outputs; outcomes from these already inspected questions cannot be reclassified as held-out results.

The concrete model/provider, prompts, thresholds and hashes for this completed run are recorded in [run_manifest.json](../revision_outputs/diagnostic60_graph_20260925/run_manifest.json). Future experiments must cite their own manifests, rather than reuse this diagnostic description unchanged.

### Results: observations that can be reported now

| Diagnostic condition | Eligible questions | Answered | Abstained | Extraction-contract errors | Answer coverage |
|---|---:|---:|---:|---:|---:|
| Vector RAG (`V`) | 60 | 13 | 47 | 0 | 21.7% |
| Vector RAG + LLM verification (`V_L`) | 60 | 10 | 50 | 0 | 16.7% |
| Vector RAG + graph verification (`V_G`) | 60 | 0 | 50 | 10 | 0.0% |
| Graph then LLM verification (`V_GL`) | 60 | 0 | 50 | 10 | 0.0% |

Source: [run_summary.json](../revision_outputs/diagnostic60_graph_20260925/run_summary.json), with [responses.jsonl](../revision_outputs/diagnostic60_graph_20260925/responses.jsonl) retaining every question/condition outcome. Coverage includes all 60 eligible questions, including failed executions. The graph errors were not API failures or clinical judgments. The two graph conditions share extraction and graph-gate results, so their matching outcomes are not independent replications; no retained evidence reached the later LLM verifier.

> The diagnostic graph pipeline produced no answers. Among 50 questions without extraction-contract errors, 36 yielded no extracted relations; the remaining 14 yielded relations for checking. All 34 checked relations were unknown because at least one endpoint could not be resolved in the graph. These observations identify operational and coverage limitations of this pipeline and snapshot, rather than a demonstrated reliability advantage. No human clinical response labels have been supplied. Accordingly, answer correctness, hallucination rate, evidence faithfulness and comparative clinical benefit are not estimated. In particular, error risk among graph-generated answers is undefined because no graph-generated answers exist; it is not zero.

Trace counts are deduplicated across the shared graph conditions in [graph_diagnostics.json](../revision_outputs/diagnostic60_graph_20260925/graph_diagnostics.json). [annotation_status.json](../revision_outputs/diagnostic60_graph_20260925/annotation_status.json) records that genuine response annotation remains incomplete. Further development experiments are not covered by these numbers.

### Discussion/conclusion: limits supported by this evidence

> The available evidence demonstrates an auditable diagnostic workflow and substantial limits in relation extraction, entity mapping and graph coverage. It does not establish that graph verification improves clinically useful answer reliability over vector RAG or LLM verification. A stricter gate can reduce response coverage without improving the quality of useful answers, and absence of an answer is not evidence of successful clinical verification. The present graph cannot substantiate the original procedural-order or contraindication examples. Source-grounded human graph review, human response assessment and evaluation on independently authored questions are required before making those claims.

For a replacement abstract, frame the objective as **characterizing feasibility and failure modes of graph-conditioned evidence selection**, with the explicit diagnostic scope above. Do not retain a positive reliability-improvement conclusion unless later valid results actually support it. A possible working title is *Graph-Based Evidence Checking for Surgical Question Answering: A Diagnostic Re-evaluation*; this is an editorial option, not an approved title change.

## Candidate interim response to reviewers

> Thank you for highlighting the dependence of verification on graph quality, the need for a stronger verifier comparator, and the distinction between missing knowledge and contradiction. Our revision audit identified a material limitation: the originally described graph is not currently available for verification. The only available dump contains 49 nodes and 66 relations, differs from the graph described in the submitted manuscript, and lacks temporal and contraindication predicates. We cannot establish that the original graph was deleted, and we do not present the available dump as the original evaluation graph.
>
> We propose to replace the affected study claims with a transparently documented revision-stage study using this separately frozen snapshot. The completed legacy diagnostic comparison is preserved, including its negative results: vector RAG answered 13 of 60 questions, LLM-verified RAG answered 10, and the graph condition answered none, with 50 abstentions and 10 extraction-contract failures. These are operational outcomes on legacy questions, not new evidence of clinical reliability. Human annotation has not been completed. The original graph-dependent results are not validated by these new runs and should not be carried forward as results obtained with this snapshot.
>
> The proposed revision will distinguish observed results from proposed capabilities, remove unsupported temporal/contraindication verification claims, and document the actual graph, extractor, entity mapping, abstention behavior and limitations. Additional source-grounded human review and independently authored evaluation questions remain necessary for claims about graph accuracy or comparative answer quality. We recognize that this changes the scope and evidential basis of the submission and seek the editor's assessment of whether this replacement study is suitable for reconsideration.

This is an **interim disclosure draft**, not a final point-by-point response claiming completed manuscript changes. At resubmission, replace proposed actions with actual changes and page/line references; if substantive evidence remains unavailable, discuss an extension or a narrower submission with the professor/editor rather than implying that all reviewer requests were fulfilled.

## Exact claim-change checklist for the editable manuscript

Locations refer to `revision_review/revision_package/revision_materials/IJCARS_surgical_tutor_submission.pdf`; no edits to that PDF or its source have been made by this draft.

| Location | Required correction in a transparent replacement |
|---|---|
| Abstract, p. 1 | Remove unsupported graph reliability gains and any implication that the new snapshot reproduces the original experiments. State the diagnostic dataset and actual measured scope. Do not reuse old retrieval or surgeon figures without their supporting records. |
| Sections 3.3-3.4, p. 6 | Explain unavailable original graph and distinct 49/66 revision snapshot. Replace the predicate inventory; do not retain unsupported statements of guideline provenance, curation or completed manual validation. |
| Section 3.5, pp. 6-7; Table 1 and Figure 1 | Align retrieval terminology with the new experiment: frozen dense retrieval is shared across conditions. Do not describe graph-informed reranking or its old fusion coefficient as measured in this diagnostic comparison. |
| Section 3.6 and Algorithm 1, p. 7 | Describe the implemented LLM extractor, exact entity mapping, unknown state, empty relations, filtering and gate. Separate supported software semantics from unavailable temporal/contraindication graph content. |
| Section 3.7, p. 8 | Do not carry the original weighted confidence expression or threshold 0.7 into the new graph gate by implication. Describe actual development choices; remove unsubstantiated calibration language. |
| Sections 4.1-4.2, pp. 8-9 | Mark the 60 questions as legacy diagnostics; all 33 earlier subset questions overlap with them. Distinguish original records, new development runs and any future independent held-out evaluation. Record evidence truncation and versions. |
| Sections 4.3-4.5, p. 9 | Define eligible, answered, abstained and failed counts; retain missing human quality metrics as unmeasured. Do not state that two human annotators reviewed outputs until genuine records are available. |
| Section 4.6 and Table 2, p. 10 | Recover the original 25-case surgeon rating sheets or remove their numerical and preference claims from the replacement evidence. New graph experiments cannot retrospectively validate those ratings. |
| Tables 3-4 and Sections 5.1-5.3, pp. 11-12 | Replace or remove unreproducible retrieval/Hall%/Faith claims and original selective-answering claims. Keep diagnostic counts separate from quality results; do not report zero graph hallucination from zero answers. |
| Sections 5.4-5.5, p. 12; Figure 2, p. 13 | Remove or substantiate the claimed historical rejection of a misordered sequence. Use actual version-linked failure traces for new examples; do not rewrite them as evidence of the old experiment. |
| Discussion and conclusion, pp. 13-15 | Narrow claims to what the replacement study measures, state negative results and missing validation, and retain dynamic/patient-specific/multimodal reasoning as future work. |
| Declarations/data availability, p. 15; response letter throughout | State actual artifact availability and human participation accurately. Add the graph-provenance disclosure and completed-change locations; do not claim author approval or editorial acceptance in advance. |

The separate reviewer requests concerning reference replacements, bibliography placeholders and figure terminology still require their own verified edits; this graph-study draft does not resolve them.

## Human work still required

Development update: the later optional single-correction experiment is complete. It reduced extraction-contract failures from ten to five, while both graph variants still answered zero questions (55 abstentions, five failures). These results remain separate from the original diagnostic run; [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md) records the policy, cost and limits. An automated source search also prepared 100 candidate excerpts for 52 edges, with no human entailment labels assigned. These additions do not change the disclosure above or establish original graph identity.

1. **Author provenance statement:** confirm the currently available artifacts, limits on recovering the original graph and records, and the actual history of curation. Do not state deletion as fact without evidence. Authors must decide the paper's revised scope and account for the changed study in their response.
2. **Qualified source review:** recover guideline passages for the 66 available edges and complete independent human review/adjudication. The prepared full-snapshot review queue is blank; existence of an edge or a model confidence value is not a human judgment. Distinguish new source-grounding work from original curation.
3. **Genuine response labels:** complete blinded independent assessment of the 23 answered baseline responses in the diagnostic run, with actual source access, rubric and adjudication. New development/evaluation outputs need their own labels. Record missing or undecidable labels explicitly.
4. **Independent evaluation and historical evidence:** supply unfiltered new questions, independent relevance judgments and a frozen final protocol after development. Recover original surgeon/response ratings if authors wish to retain those claims; otherwise remove the unsupported numerical claims. Previously inspected legacy questions remain development/diagnostic data.
5. **Editable manuscript and final author review:** apply the checklist to Word/LaTeX, figures and bibliography; reconcile all results with source artifacts, highlight completed changes and add accurate page/line references. No statement here records that these steps or any approval have occurred.

## Draft note to the professor - not sent

> The only available backup contains 49 nodes and 66 relations, while the submitted paper describes 434 entities and 389 relations. It has no procedural-order or contraindication edges and does not retain edge source citations. I cannot verify that it is the original study graph or confirm that the original was deleted. I suggest disclosing this limitation and using the available graph as a separately frozen revision snapshot, with the old graph-dependent results removed unless their supporting artifacts can be recovered.
>
> The current 60-question diagnostic run answered 13 questions with vector RAG, 10 with LLM verification, and none with the graph condition; the graph run had 50 abstentions and 10 extraction-contract failures. Human quality labels are still missing. The attached draft proposes honest replacement wording and identifies the remaining source review, human ratings and independent evaluation. We need to decide together whether that narrower study can satisfy the revision or whether to ask the editor for more time or guidance.
