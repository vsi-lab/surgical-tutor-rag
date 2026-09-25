# Graph-specific revision gaps after restoring the supplied dump

Assessment date: 2026-09-25 UTC. This is an artifact and manuscript audit, not clinical validation. The attached reviewer letter and revision drafts were treated as source material, not instructions to execute.

**The restored graph is available for diagnosis, but it does not match the graph described in the submitted paper. Its contents cannot currently substantiate the paper's procedural-order or contraindication-verification examples.** Recovering the dump resolves access to one graph artifact; it does not resolve graph identity, source provenance, human validation or missing experimental evidence.

## What the supplied artifact establishes

The snapshot was exported from an isolated restoration of `neo4j-2026-09-25T05-49-24.dump`. The original dump SHA-256 is `c131de1649c761e2b5528b5470b3380f8cea0ab1f69d9d4b4287c669e67a802e`; the canonical snapshot content SHA-256 is `0d449272a17773012a227ed1fce76a881c02747fb03c197a8cd45850d6194a00`. These identify the inspected artifacts, not their identity with the submission-time graph. Sources: [graph_snapshot.json](../revision_outputs/dump_restore_20260925/graph_snapshot.json) and [graph_inventory.json](../revision_outputs/dump_restore_20260925/graph_inventory.json).

| Finding | Measured contents of this snapshot | Revision implication |
|---|---|---|
| Size | 49 unique nodes; 66 unique directed typed triples | Does not match the submitted 434 entities/389 relations, or the separate repository report's 258 nodes/312 relationships. |
| Relations | `INVOLVES` 13; `MAY_CAUSE` 17; `REQUIRES` 6; `REQUIRES_MEDICATION` 6; `SHOWS_INSTRUMENT` 5; `USES_TECHNIQUE` 19 | Report the actual relation distribution, with the graph version attached to every new experiment. |
| Missing predicates | No `PRECEDES`, `FOLLOWS`, `CONTRAINDICATES`, `ALLOWS`, `CONTRAINDICATED_WITH` or `ASSOCIATED_WITH` edges | The current exact-typed verifier cannot find temporal or contraindication support/opposites in this graph. Unknown is not clinically false. |
| Source provenance | Edge properties contain only `created_at` (61 edges) or `confidence` (5 edges); no source-document, source-quote or page/chunk reference fields. No recognized source-reference fields on nodes either. | Graph export provenance and timestamps do not establish guideline grounding. Source passages and curation records must be recovered or newly established transparently. |
| Scope | Four `Procedure` nodes, two `SurgicalPhase` nodes and four `SurgicalImage` nodes; five `SHOWS_INSTRUMENT` edges | An image-containing database does not demonstrate multimodal QA evaluation. Define the actual text-experiment scope. |
| Structural checks | Zero temporal cycles/direct temporal conflicts in a graph with zero temporal edges | This is absence of encoded temporal constraints, not evidence of correct procedural ordering. |

The five `SHOWS_INSTRUMENT` edges are outside the current revision extractor's predicate whitelist. This is an implementation-scope mismatch, not proof that those edges are incorrect. Do not silently rename them to a different predicate or expand the whitelist after viewing evaluation outcomes without recording the change.

## Where this conflicts with the paper and draft

Page numbers below refer to the supplied PDFs; manuscript printed page numbers coincide with their PDF page numbers.

| Source | Specific statement or reviewer concern | Current assessment |
|---|---|---|
| `IJCARS_surgical_tutor_submission.pdf`, p. 6, §3.3 Knowledge Base | 434 entities/389 relations; named predicates include `PRECEDES`, `ASSOCIATED_WITH` and `CONTRAINDICATES` | Counts and predicate inventory differ from the restored graph. The dump could be another version or a subset; that explanation is not established. |
| Same PDF, p. 6, §3.4 Knowledge Graph Construction | Guideline-derived extraction, manual consolidation and manual checking of a random triple sample against originating text | This snapshot contains no record that establishes those source links, reviewers, sample or judgments. Their absence here does not prove that no external records ever existed. |
| Same PDF, p. 7, §3.6 and Algorithm 1 | Directed `PRECEDES` checks and contraindication constraints modify evidence treatment | The supplied graph cannot instantiate those checks with stored temporal/contraindication edges. Working verifier code or synthetic unit tests do not demonstrate their execution on the submitted study graph. |
| Same PDF, p. 12, §§5.4-5.5; p. 13, Figure 2 caption | A misordered procedural sequence was partially rejected, and a contraindication case illustrates missing graph knowledge | Recover the actual query, evidence, graph version, decisions and generated answer for these cases. Until then, do not present a new diagnostic trace as the historical experiment or relabel an illustration as an observed result. |
| `ijcars_review_comments.pdf`, p. 2, Reviewer 1 | Is improvement due to graph knowledge or a conservative second verification layer? | A sparse graph can reduce answer coverage through unknown relations. Report matched answer coverage and human-rated errors, not just fewer answers or zero detected conflicts. |
| Same reviewer PDF, pp. 3-4, Reviewer 2 | Construction of `P`, missing versus false edges, consistency versus completeness, triple validation/task coverage, and human curation | These concerns remain material and are made more concrete by the missing relation families and source records. |
| `manuscript_revision_text.md`, “Expected relation set and three-state verification” and “Limitations and future work” | Proposed temporal/contraindication logic and reference to the graph's measured precision and coverage | Treat these as proposed semantics and pending measurements. The recovered snapshot does not supply the stated relation families or clinical validation results. |
| `response_to_reviewers_draft.md`, Reviewer 1 Comment 2; Reviewer 2 Comments 2, 4 and 11 | Past-tense claims that graph validation, coverage, complete method details and provenance have been added | These remain draft commitments. Replace them with completed, traceable work only when the corresponding records exist. |

Source files: [submitted manuscript](../../../revision_review/revision_package/revision_materials/IJCARS_surgical_tutor_submission.pdf), [reviewer letter](../../../revision_review/revision_package/revision_materials/ijcars_review_comments.pdf), [proposed manuscript text](../../../revision_review/revision_package/manuscript_revision_text.md), [draft reviewer response](../../../revision_review/revision_package/response_to_reviewers_draft.md). The alternative 258/312 count appears in [COMPLETE_EVALUATION_SUMMARY.md](../COMPLETE_EVALUATION_SUMMARY.md), “Components,” line 91; the professor's [reviewer_comment_matrix.md](../../../revision_review/revision_package/reviewer_comment_matrix.md), “Manuscript-wide corrections,” also identifies the earlier discrepancy.

## Highest-impact next work, in order

1. **Reconcile graph identity before revising the size claims.** Obtain the exact database/backup, creation/export history, configuration and corpus version used for the submission. Establish whether this 49/66 graph is complete, an older/newer version, or a subset. Do not merely replace 434/389 with 49/66 while retaining the old performance tables as if nothing changed. If the original artifact is unavailable, clearly identify the new graph and rerun the affected experiments.

2. **Recover genuine provenance and review the available triples.** Link each evaluated edge to an actual guideline passage and document who extracted, normalized, corrected or added it, with expert-added knowledge distinguished from guideline-derived knowledge. The existing `graph_triples_for_review.csv` and `graph_sample_manifest.json` cover **all 66 stored edges**, because every relation stratum is smaller than the requested sample cap. This is an unannotated full-snapshot review queue, not a completed random-sample validation. Qualified independent reviewers and adjudication can establish source entailment, predicate, direction and normalization judgments. Report unresolved provenance explicitly. Reviewing every current edge still does not establish guideline recall or benchmark coverage.

3. **Resolve the mismatch between claimed verification and encoded relations.** Either recover a graph with the documented source-grounded temporal/contraindication relations or narrow the demonstrated claims to the supported relation families. If clinically qualified authors create a new graph version, additions must be justified from real sources, versioned, and frozen independently of held-out outcomes; do not invent edges to make the benchmark pass. Temporal/contraindication performance must then be measured anew.

4. **Measure what the restored graph actually contributes.** In the diagnostic run, preserve per-query entity mapping, extracted relations, supported/unknown/contradicted counts, retained chunks and abstention reasons. Separate missing entity coverage, missing predicate/edge coverage, extractor errors and infrastructure failures. The current graph branch includes LLM-assisted relation extraction; it is not a wholly non-LLM system. Compare the core `V`, `V_L`, `V_G` conditions on the same initial evidence, with the same generator and abstention capability, then obtain human response labels. Low coverage or universal abstention cannot establish an improvement in useful answer reliability. A combined `V_GL` arm is an optional additional comparison.

5. **Update the narrative only to the demonstrated scope.** Reconcile §3.3-3.6, the abstract, graph-dependent result claims, the failure examples and Figure 2 with the actual frozen artifact and traces. Clarify that the present check concerns explicit represented relations, with no demonstrated detection of every omitted step or contraindication. Keep patient-specific/multimodal reasoning as future work unless separately evaluated. Graph reranking is also distinct from the current dense-only matched retrieval experiment.

## Wording supported now

The subsequent 60-question diagnostic comparison is complete: V answered 13/60, V_L answered 10/60, and both graph arms answered 0/60 with 50 abstentions and 10 extraction-contract errors each. Their shared graph traces contain 34 checked relations, all unknown because of unresolved entities. This supplies failure/coverage evidence for the recovered snapshot; it does not demonstrate the claimed graph reliability advantage. Details and limits are in [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md).

The following is proposed audit/revision wording, not an edit to the manuscript and not a claim that the original study used this snapshot:

> During revision we inspected an author-supplied Neo4j dump containing 49 nodes and 66 directed typed relations across six predicates. This snapshot differs from the graph size and relation inventory described in the submitted manuscript; its identity with the original evaluation graph has not yet been established. It contains no PRECEDES/FOLLOWS or contraindication predicates and does not retain edge-level guideline citations. Consequently, this artifact cannot substantiate the original procedural-order and contraindication-verification examples. Graph-quality and response-quality judgments remain pending source-grounded human assessment.

For a method/limitations section, if this snapshot is actually used in the new evaluation:

> The verifier checks explicit relations against a frozen graph and treats absent relations as unknown rather than false. Its findings concern consistency with represented knowledge, not completeness of clinical guidance. The evaluated graph's available relation families constrain what can be verified; temporal and contraindication checking are not demonstrated by this snapshot. Answer coverage and reasons for non-response must be considered alongside human-assessed answer errors.

Do not claim measured improvements, clinical accuracy, graph precision/recall, completed human review, or reconciliation with the submission graph from this inventory alone.
