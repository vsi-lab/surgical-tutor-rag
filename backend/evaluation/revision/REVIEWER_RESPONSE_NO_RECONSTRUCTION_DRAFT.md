# Response to Reviewers — conservative draft without reconstruction results

**Internal status:** This draft deliberately excludes every graph count and experimental result produced from the revision-stage reconstruction. It does not substitute estimated, simulated, or manuscript-derived values for a missing matched experiment. Page and line references must be added after the editable manuscript is revised.

Manuscript: CARS-D-26-00804 (identifier in the review letter; verify the current resubmission identifier before use)
Title: *Reliable Surgical Question Answering through Graph-Based Evidence Verification*

Dear Editor and Reviewers,

We thank the reviewers for the detailed methodological and reporting recommendations. During revision, we determined that the preserved submission artifacts are insufficient to verify the graph-specific aggregate results or to conduct the requested matched graph-versus-LLM comparison in the submission-time experimental environment. We therefore will not present the previously reported aggregate values as newly reproduced results, and no later graph reconstruction is used as a proxy for the submitted graph. The revised manuscript will distinguish verified method definitions from empirical claims, remove results that lack supporting per-query records, and identify the requested confirmatory experiments as outstanding.

## Reviewer 1

### Comment 1 — Compare graph verification with LLM self-verification

**Response.** We agree that the vector-only comparison does not isolate the value of explicit graph constraints from the more general effect of adding a conservative verifier. The appropriate matched design contains four conditions:

1. vector retrieval and generation;
2. vector retrieval followed by LLM evidence verification;
3. vector retrieval followed by graph verification; and
4. vector retrieval followed by graph verification and then LLM evidence verification.

All four conditions must receive the same questions, initially retrieved passages, answer generator, decoding settings, and evidence budget. Answer coverage, execution failures, correctness, unsupported claims, procedural inconsistencies, clinically important omissions, and faithfulness must be reported separately. Paired human judgments are required to determine whether greater abstention corresponds to lower error risk.

We do not have a valid matched result from the submission-time graph for this comparison. The manuscript will therefore remove the claim that the present evidence establishes a unique reliability benefit from graph verification. We will report this comparison only after it is run on a frozen, source-validated graph with an independently frozen evaluation set and blinded clinical annotations. Values from the submitted paper will not be relabeled as outcomes of this new ablation.

### Comment 2 — Graph quality, construction, curation, and robustness

**Response.** We agree that graph quality is a determinant of verifier behavior. A missing relation can cause a conservative system to reject relevant evidence, while an incorrect relation can certify an inappropriate claim or produce an incorrect veto. Structural database counts alone do not establish clinical validity.

The revised manuscript will not retain claims of manual graph validation, relation precision, guideline coverage, or robustness unless the corresponding source-linked records are available. A defensible validation will use a prespecified, relation-stratified sample. Qualified reviewers will independently judge entity normalization, relation type, direction, and entailment by the cited guideline passage, followed by documented adjudication. Completeness will be assessed separately by sampling source statements or evaluation tasks and determining whether their required entities and relations are represented.

An edge-deletion or corruption experiment will be reported only after the graph, entity linker, evaluation set, and clinical outcomes are frozen. The perturbation level, sampling method, random seeds, and effect on both coverage and clinical error must be reported.

### Comment 3 — Dynamic neuro-symbolic and situational reasoning

**Response.** We will add this as prospective work. A future system could maintain a situational graph containing patient anatomy, operative phase, completed steps, intraoperative findings, complications, and available interventions. Conflicts between retrieved evidence, graph constraints, and model reasoning could trigger targeted retrieval or a request for missing context. Imaging, video, and instrument tracking will be described as future extensions; they were not evaluated in the submitted text-based study.

## Reviewer 2

### Comment 1 — Role of the graph and retrieval terminology

**Response.** We agree that the manuscript conflated graph-informed reranking with post-retrieval graph verification. The revised Methods will define them as separate operations:

- **Graph-informed reranking** changes the order of candidates returned by dense retrieval.
- **Graph verification** evaluates typed claims extracted from a retrieved candidate before that candidate can be supplied to the answer generator.

The terms “graph retrieval,” “graph-enhanced retrieval,” and “graph verification” will not be used interchangeably. Any retained reranking claim will require an executable scoring definition and a separate retrieval evaluation.

### Comment 2 — Expected relations, directionality, empty sets, and filtering

**Response.** We will specify the verification unit as a retrieved candidate passage. For question \(q\) and passage \(d\), the expected-relation set is

\[
P(q,d)=\{(u_i,r_i,v_i,z_i)\}_{i=1}^{m},
\]

where \(u_i\) and \(v_i\) are directed entity mentions, \(r_i\) is a declared predicate, and \(z_i\) identifies the passage and exact supporting span. The extractor may not treat the question as an asserted fact, infer order from an unordered list, or introduce an undeclared predicate. Direction is preserved; for example, `A FOLLOWS B` is canonicalized as `B PRECEDES A`.

Each valid relation has one of three states:

- **supported:** the exact directed typed relation is present;
- **contradicted:** an explicitly encoded opposing relation is present; or
- **unknown:** an entity is unresolved, or neither the asserted relation nor an explicit opposite is present.

An empty \(P(q,d)\) cannot certify a passage. Verification is applied independently to each candidate. A rejected passage is removed in full, and the answer generator receives only passages that pass the declared gate. These rules define a revised evaluation protocol; they are not presented as a reconstruction of the decision path that produced the submitted aggregate values.

### Comment 3 — Missing graph edges and completeness

**Response.** We agree that absence of a graph edge is not evidence of clinical falsity. Missing or unresolved relations will be classified as unknown rather than contradicted. An explicit encoded opposite is required for contradiction.

The manuscript will also distinguish consistency from completeness. Checking relations stated in a passage cannot detect an omitted mandatory step or contraindication unless the method separately expands the procedure into a validated set of required relations. Claims that the current method proves evidence completeness will be removed.

### Comment 4 — Graph validation and task coverage

**Response.** We will distinguish four quantities: structural inventory, source-grounded relation precision, source-statement coverage, and operational coverage on the evaluation questions. None can substitute for another.

We will not report a clinical graph-quality percentage without completed source review. Any future result will provide the sampling frame, sample size, relation-wise counts, reviewer qualifications, independent judgments, agreement, adjudication, and confidence intervals. Operational coverage will report how often entities resolve, how many expected relations are supported, contradicted, or unknown, and how many questions retain at least one passage.

### Comment 5 — Score definitions, aggregation, and the graph gate

**Response.** The submitted meanings and aggregation rules for `S_coverage` and `S_agreement` cannot be verified from the preserved per-query artifacts. We will remove those terms rather than assign them retrospective definitions.

For a future rerun, we propose explicitly named relation-level quantities:

\[
S_{relation\_support}=\frac{n_{supported}}{n_{supported}+n_{contradicted}}
\]

when at least one relation is known, and

\[
S_{relation\_coverage}=\frac{n_{supported}+n_{contradicted}}{|P|}.
\]

When \(|P|=0\), relation support is undefined and relation coverage is zero. Thresholds, veto behavior, passage-level aggregation, and the rule for reaching answer generation will be declared before evaluation. A hard-gate versus soft-score comparison will be reported only after outcome labels are available.

### Comment 6 — Calibration, weights, thresholds, and the confidence figure

**Response.** We agree that a weighted support score is not automatically a calibrated probability. The terms “confidence-calibrated” and “optimal” will be removed unless supported by a prespecified development/evaluation split and appropriate calibration measurements.

The submitted fusion weights and threshold will not be described as optimized without a reproducible sweep. The confidence-versus-error figure will be removed unless regenerated from labeled held-out data with bin definitions, observations per bin, and uncertainty. Any future operating threshold will be selected using development data before the final evaluation is opened.

### Comment 7 — Retrieval corpus, relevance judgments, and Recall@5

**Response.** We agree that retrieval results require a clearly defined corpus and relevance judgments assigned independently of the evaluated rankings. The preserved labels contain identity and selection problems and do not support the submitted perfect Recall@5 claim. We will withdraw that claim rather than reuse it under a changed evidence-identity scheme.

A replacement evaluation will use globally unique evidence identifiers, report corpus and deduplication rules, permit multiple relevant passages where appropriate, and provide per-query rankings. Recall@5, MRR, MAP, and NDCG will be computed only from independently assigned relevance judgments.

### Comment 8 — Hallucination denominator, coverage, and error categories

**Response.** We agree that answer coverage and error risk must be reported together. The preserved response-level evidence is insufficient to reconstruct the submitted hallucination percentages, so those percentages will not be retained as validated measurements.

In a future labeled evaluation, answer coverage will be the number of answered questions divided by all eligible questions. Execution failures and abstentions will remain visible and will not be counted as correct answers. Error risk will be reported among answered responses with raw counts. Unsupported factual claims, procedural inconsistencies, and clinically important omissions will be annotated and reported separately, with overlap permitted where justified.

### Comment 9 — Faithfulness, the 33-question subset, and NoAnswer outcomes

**Response.** We will define claim-level faithfulness as the number of human-supported factual claims divided by the number of human-assessed factual claims. It is undefined when no factual claim is produced and is distinct from correctness against the wider guideline corpus.

The smaller question subset is not an independent evaluation because it overlaps the larger benchmark and was affected by prior retrieval inspection. It will not be presented as held-out confirmation. Future non-answer reporting will distinguish intentional abstention, extraction or execution failure, empty expected-relation sets, unresolved entities, insufficient graph coverage, explicit contradiction, and graph conflict.

### Comment 10 — Multimodal framing, figures, terminology, and bibliography

**Response.** We will remove multimodal and visual-question-answering language from the evaluated system description. Figure 2 will be removed or labeled explicitly as a conceptual example after its Critical View of Safety terminology is checked against the cited clinical source. The unexplained “Fat stem score” label will be removed. No figure will be presented as an observed graph-verification trace without a preserved per-query record.

### Comment 11 — Human role in graph construction

**Response.** We agree that the number and qualifications of curators, their instructions, permitted operations, and adjudication procedure must be reported. The preserved records do not substantiate those details for the submission-time graph, so the manuscript will not state that a particular manual validation process occurred.

Any new curation will be prospective and logged at relation level. The record will distinguish normalization or extraction correction from an expert-added relation, identify the supporting source passage, preserve independent judgments, and document adjudication.

## Editor

### Comment — Replace non-peer-reviewed arXiv references, especially References 14–16

**Response.** We agree. References 14–16 will be removed in their current form, together with any sentence that depends specifically on an unsupported claim from those works. Replacement sources will be peer-reviewed journal articles whose contents directly support the revised sentence. Conference-proceedings papers will not be presented as satisfying the editor’s journal-source request. Placeholder metadata elsewhere in the bibliography will be corrected according to journal style.

## Required work before this response is submission-ready

1. Apply the proposed changes to the editable manuscript and insert page and line references.
2. Complete the matched four-condition experiment using a frozen, source-validated graph and independently frozen evaluation set.
3. Obtain blinded clinical labels for answer correctness, unsupported claims, procedural errors, omissions, and faithfulness.
4. Complete source-grounded graph validation and task-coverage assessment.
5. Replace or remove unsupported retrieval, hallucination, selective-answering, calibration, and user-study results.
6. Verify the current manuscript identifier and every replacement journal citation.

Until this work is complete, the scientifically supportable response is to narrow or withdraw the affected claims rather than substitute estimated values.
