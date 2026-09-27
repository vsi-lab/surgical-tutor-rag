# Rebuilt-graph experiment comparison

The 115-node/382-relationship reconstruction was evaluated on the same frozen 60-question legacy evidence used for the earlier 49-node/66-relationship graph diagnostic. The operational results are unchanged. This is a diagnostic comparison, not a reproduction of the submitted paper's aggregate results.

## Frozen comparison

- Same 60 query IDs and retrieved passages; evidence SHA-256 `7840af30b8eda2de742ed01ae09fab227939dba0481e7e9f60f17974b4236e22`.
- Same `openai/gpt-4o` request payloads, prompts, temperature 0, 2,400-character evidence cap, and graph thresholds (`min_support=1.0`, `min_coverage=1.0`). Prompt SHA-256 `67a342ea72a797b5a2a8e6d448157520f4b2116d05722cb59924e9f6980b18a8`.
- Old snapshot: 49 nodes/66 relationships, file SHA-256 `94a02cefa753092c99601b9c02fbf2c113890fea37f4e1b23576145538063eb2`.
- Rebuilt snapshot: 115 nodes/382 relationships, file SHA-256 `05efde547935d0d2079f42e90f9d1bcc04c834adec2ac8e6d68160c3b4341027`.
- The old model-call logs were copied as an exact-request cache. Both resulting logs remained byte-identical to their source logs, proving that the comparison made zero new model calls and incurred zero incremental provider-reported cost. Cumulative cost fields in run summaries include the archived seed and must not be counted again.
- The current runner adds extraction-attempt audit fields. Its first-attempt prompts and default acceptance policy are unchanged; the prompt hash matches the original run. Comparison uses semantic fields and ignores latency, snapshot checksum, and database-internal node identifiers.

## Primary comparison: no extraction repair

| Condition | Old answered / abstained / errors | Rebuilt answered / abstained / errors | Changed rows |
|---|---:|---:|---:|
| `V` | 13 / 47 / 0 | 13 / 47 / 0 | 0 |
| `V_L` | 10 / 50 / 0 | 10 / 50 / 0 | 0 |
| `V_G` | 0 / 50 / 10 | 0 / 50 / 10 | 0 |
| `V_GL` | 0 / 50 / 10 | 0 / 50 / 10 | 0 |

Across all 240 query/condition records there were zero status, reason, answer, initial-evidence, or retained-evidence changes. One hundred completed graph traces were compared. After excluding the intentionally different snapshot checksum and internal Neo4j/reconstruction IDs, every graph decision was identical.

For the 50 non-error graph queries, 232/250 chunk occurrences had no extracted relation and 18/250 failed graph coverage. All 34 unique relations reaching the checker were `unknown` because at least one endpoint was unresolved. Only one source endpoint (`ultrasound`) resolved in each graph; all 34 targets and 33 other sources were unresolved. The internal ID for `ultrasound` differs between snapshots, but the unknown decision and rejected chunk are the same.

Artifacts: [old summary](../revision_outputs/diagnostic60_graph_20260925/run_summary.json), [rebuilt summary](../revision_outputs/rebuilt_graph_diagnostic60_20260926/run_summary.json), [rebuilt diagnostics](../revision_outputs/rebuilt_graph_diagnostic60_20260926/graph_diagnostics.json), and [structured comparison](../revision_outputs/rebuilt_graph_comparison_20260926/comparison.json).

## Development comparison: one graph-blind schema repair

| Condition | Old answered / abstained / errors | Rebuilt answered / abstained / errors | Changed rows |
|---|---:|---:|---:|
| `V` | 13 / 47 / 0 | 13 / 47 / 0 | 0 |
| `V_L` | 10 / 50 / 0 | 10 / 50 / 0 | 0 |
| `V_G` | 0 / 55 / 5 | 0 / 55 / 5 | 0 |
| `V_GL` | 0 / 55 / 5 | 0 / 55 / 5 | 0 |

The same holds for this 240-record development run: no status, reason, answer, evidence, or semantic graph-decision change. Among the 55 non-error graph queries, 251/275 chunk occurrences had no extracted relation and 24/275 failed graph coverage. All 43 checked relations remained unknown due to unresolved entities. Only the same `ultrasound` source resolved; all 43 targets and 42 other sources did not.

Artifacts: [old development summary](../revision_outputs/development_repair_20260925/run_summary.json), [rebuilt development summary](../revision_outputs/rebuilt_graph_development_repair_20260926/run_summary.json), and [rebuilt development diagnostics](../revision_outputs/rebuilt_graph_development_repair_20260926/graph_diagnostics.json).

## Interpretation

The larger reconstructed graph produced no improvement because the verifier uses exact/alias entity resolution and full relation coverage. None of the extracted relations was fully resolvable in either graph. Consequently, the graph gate retained no evidence, and neither graph arm generated an answer. This result demonstrates a vocabulary/entity-resolution mismatch; it does not show that the two graphs are equivalent.

The unchanged outcomes apply only to these new, fully archived 60-question diagnostics. They do not validate the submitted manuscript's MAP, Recall@5, NDCG, hallucination, coverage, surgeon-rating, graph-precision, or graph-recall numbers. Those metrics use different definitions or require relevance judgments and human labels that this run does not contain. Human clinical quality remains undefined.

Improving normalization or adding edges after inspecting these 60 questions would be development work. Any such changes must be source-grounded, versioned, and tested on a separately frozen set before making confirmatory claims.
