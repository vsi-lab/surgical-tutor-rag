# Human annotation for the revision

This workflow prepares blinded response sheets and summarizes labels entered by people. It does not supply clinical judgments, establish graph quality, or certify reviewer expertise. The numerical values in unit tests are synthetic software fixtures and must never enter the paper.

## Freeze the evaluation before reviewing answers

Keep development and held-out questions separate. Freeze the question manifest, graph and corpus versions, prompts, model identifiers, thresholds and run configuration before evaluation. Prespecify the conditions: the default core comparison is `V`, `V_L`, `V_G`; the combined `V_GL` arm is optional. Run each declared condition on the same questions. Preserve one record for every question and condition, including infrastructure errors. Do not drop difficult questions, remove failed runs selectively, or tune prompts after inspecting held-out answers.

The runner JSONL must contain `query_id`, `question`, `condition`, `split`, `status`, `answer`, and `evidence`. Status is `answered`, `abstained`, or `error`. Evidence is a list of objects containing at least `source` and `text`. Additional metadata stays in the original run. Question IDs must occur in one split only. An answered record needs nonempty question and answer text. A retrieval failure caused by unavailable infrastructure belongs in `error`, rather than an intentional scientific abstention.

## Export sheets

From the repository root:

```powershell
python -m backend.evaluation.revision.annotations export --input artifacts/run.jsonl --output artifacts/blinded.csv --mapping artifacts/private_mapping.json --seed 2026 --expected-conditions V,V_L,V_G
```

The output CSV contains opaque shuffled IDs, question, answer, source evidence, and blank human rating fields. Neutral chunk IDs accompany display labels (`E1`, `E2`, etc.) so reviewers can resolve citations in the original answer. It excludes condition names, query IDs, similarity scores, traces, timing and token usage. Only answered responses need response ratings; all run records remain available for coverage and failure counts. Save the private mapping and original run separately from the reviewers' sheets. The seed and mapping are private; blinding does not mean the answer wording itself cannot reveal aspects of the system.

The mapping freezes the declared expected conditions. An interim run containing only `V,V_L` should still declare `V,V_L,V_G` when the graph comparison is planned, so the report identifies the absent graph arm. Use `--expected-conditions V,V_L,V_G,V_GL` for a planned four-condition comparison. Do not shrink the declaration after inspecting outcomes to make an incomplete comparison appear complete. Runs containing a condition outside the declared set are rejected.

Choose new output paths for each export: the command refuses to overwrite existing sheets or mappings. Preserve the exported question, answer and evidence text exactly. The report verifies both the frozen run digest and this content. Spreadsheet software can alter long cells; if it does, correct the export/import process rather than changing the frozen answer.

## People and source material

Use two qualified human reviewers working independently with separate copies of the same blinded sheet. Establish the rubric on development examples before held-out annotation. Report their actual qualifications and any overlap with graph curation, benchmark writing or system development. Never invent a second reviewer or describe an automated model as a human assessor.

Give both reviewers the same frozen guideline/source corpus and any prespecified reference evidence. Retrieved text can establish whether a stated claim has supplied support, but is insufficient by itself to establish that the answer contains all clinically important information. Critical omissions and correctness require source-grounded assessment of the question. If the sources are insufficient or the reviewer cannot decide, leave the relevant rating blank, explain why in comments, and seek qualified adjudication. Blank does not mean no error.

Keep both original reviewer sheets unchanged. Discuss disagreements through a qualified adjudicator while retaining blinding to condition. Save one final adjudicated CSV with exactly one row per annotation ID; identify the responsible adjudicator in `annotator_id` and preserve the decision trail in comments or a separate record. If the initial reviewers agree, the final record may identify them jointly. The report consumes this single final sheet; concatenating independent sheets creates duplicate IDs and is rejected. Report initial agreement and disagreement counts separately from adjudicated outcomes; this module does not compute inter-rater reliability.

## Rating fields

All binary ratings use literal `0` or `1`; blank means unassessed or unresolved. Enter the human `annotator_id` for every row with any ratings.

| Field | Human judgment |
|---|---|
| `unsupported_claim` | `1` if at least one substantive factual claim lacks support under the prespecified evidence-support rubric; `0` only after reviewing the whole response. This is a support judgment, not an automated similarity threshold. |
| `procedural_error` | `1` if at least one clinically material procedural-order or procedural-consistency error is established against the frozen sources; otherwise `0`. |
| `critical_omission` | `1` if a source-grounded, clinically important qualification, contraindication or procedural element needed to answer this question is omitted; otherwise `0`. Do not mark every conceivable detail as required. |
| `correct` | `1` if the response meets the prespecified overall answer-correctness rubric; `0` otherwise. Assess separately from evidence faithfulness and from any individual error label. |
| `supported_claims` | Optional human count of factual claims supported by the evidence, using an agreed claim segmentation and support rubric. |
| `total_claims` | Optional total count of assessed factual claims. Supply both counts or neither; `0 <= supported_claims <= total_claims`. A response with no factual claims has `0,0`, which gives undefined faithfulness. |
| `comments` | Source/page citations, reason for an unresolved label, disagreement resolution and other relevant review notes. Avoid personal patient information. |

Define in the manuscript whether support refers to the evidence actually supplied to the generator or the wider source corpus, and apply that definition consistently. A useful distinction is supplied-evidence faithfulness versus guideline-grounded correctness/omissions. A clinically correct statement may be unsupported by the retrieved evidence. Conversely, faithful repetition of incomplete evidence can still omit critical information. Do not derive a hallucination label as `1 - faithfulness`.

## Produce a report

```powershell
python -m backend.evaluation.revision.annotations report --input artifacts/run.jsonl --mapping artifacts/private_mapping.json --annotations artifacts/adjudicated.csv --output artifacts/annotation_report.json
```

The report separates development and evaluation splits and shows every condition. Duplicate/unknown IDs, duplicate run cases, changed evidence, invalid labels, and impossible claim counts are errors. Missing rows or blank labels produce an explicitly incomplete report. A report can be generated during annotation, but its presence does not mean annotation is finished.

- **Eligible denominator:** all question IDs present anywhere within the split, with the declared expected conditions. An entirely absent question cannot be detected from JSONL alone; reconcile the run against the frozen dataset manifest before publication. Missing individual condition records are flagged and coverage remains undefined until resolved.
- **Coverage:** answered / all eligible questions. Infrastructure errors stay in the denominator and appear as separate failure counts/rates; they are never relabeled abstentions or safe responses.
- **Hallucination risk among answered:** responses with any of the three error labels / answered responses. The categories can overlap; a response with two error categories contributes once to overall risk. If any answered response lacks a required error label, the main risk is undefined. Labeled-subset statistics are explicitly partial and cannot substitute for the complete result.
- **Correctness:** reported independently among answered responses, with the same missing-label protection. Report coverage alongside it.
- **Faithfulness:** optional micro average of human-supported claims / total human-counted claims. Partial counts stay explicitly labeled as a subset. The report does not calculate a binomial confidence interval over pooled claims because claims within a response are dependent.
- **Uncertainty:** descriptive two-sided 95% Wilson intervals accompany response-level binomial rates. They are not paired between-system tests or proof of superiority. Use appropriate paired analysis over common questions for comparative claims; system-specific answered subsets differ when abstention differs.

Check `matched_run_complete`, `annotations_complete`, and `complete_for_primary_descriptive_reporting`, together with counts, failures and all missing-value fields. A true completeness flag only describes the available records and fields: it does not establish unbiased sampling, adequate sample size, expert review quality, or clinical safety. Retain the frozen run, private mapping, independent sheets, adjudicated sheet, rubric and source versions as the audit trail.

## Separate graph triple review

An available graph snapshot can also be sampled for human review:

```powershell
python -m backend.evaluation.revision.graph_audit --graph artifacts/graph_snapshot.json --output artifacts/graph_triples.csv --manifest artifacts/graph_sample_manifest.json --per-relation 25 --seed 2026
```

The helper accepts the `nodes`/`edges` format in `GRAPH_VERIFIER_FORMAT.md`. It draws up to the specified number of stored edges uniformly without replacement from each relation type, retaining rare relation types, source/target node properties and edge provenance. The sample size is a configurable starting point, not a claim of statistical adequacy. The manifest records population and sample counts, seed, edge indices and checksums. An accessible current database is not automatically the graph used for the submission; author confirmation and historical records are still needed.

Have qualified reviewers independently enter `source_entails`, `relation_correct`, `direction_correct` and `normalization_correct` as `0`/`1`, with source citations and adjudication as above. These fields assess actual source support, correct predicate, correct orientation and correct entity mapping. Missing source provenance must be recovered or recorded as unresolved; never infer source entailment from the existence of a graph edge. All labels are exported blank and no graph-quality percentage is produced automatically.

Preserve independent sheets and an adjudicated sheet before calculating graph-quality results. Report relation-specific counts, sample design and agreement; if estimating whole-graph precision from equal-sized relation strata, weight strata by their graph population rather than pooling them indiscriminately. Sampling stored edges estimates precision, not recall or task coverage. Those require separate source-statement/question-based coverage assessment. Duplicate stored edges remain explicit sampled records and must not silently be presented as independent unique clinical facts.
