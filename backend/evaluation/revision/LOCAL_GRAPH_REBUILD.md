# Local graph rebuilt from saved chunks

Completed on 26 September 2026. The complete saved corpus produced **115 unique nodes and 382 unique relationships**, which were loaded into a separate local Neo4j database. That local service is now stopped and preserved. The same validated snapshot was subsequently imported into the configured Aura database, and `backend/.env` now points to Aura; see [AURA_DEPLOYMENT.md](AURA_DEPLOYMENT.md). The original Desktop database and supplied 49-node/66-relationship dump were preserved.

This is a reconstruction using surviving text and construction code. It does not establish identity with the deleted cloud database, restore historical manual curation, or validate the paper's previous performance results.

## Measured results

| Artifact | Input scope | Unique nodes | Unique relationships |
|---|---|---:|---:|
| Supplied September dump | Previously restored local graph | 49 | 66 |
| February upload replay | 10 successful uploads, 967 chunks, 8 distinct texts | 92 | 272 |
| Full recovered corpus; preserved local database and active Aura copy | 20 source names, 1,314 canonical chunks, 18 distinct texts | 115 | 382 |

The full reconstruction contains 140 `INVOLVES`, 62 `MAY_CAUSE`, 18 `REQUIRES`, 48 `REQUIRES_MEDICATION`, and 114 `USES_TECHNIQUE` relationships. It has no `PRECEDES`, `FOLLOWS`, or `CONTRAINDICATES` relationships: the original construction path does not insert them. A larger graph alone does not demonstrate improved answers.

### What the paper's 434/389 figures mean

The saved [February upload summary](../results/bulk_upload_summary.json) reports totals of 434 nodes and 389 relationships. Those figures exactly match the manuscript's figures. However, [the ingestor](../../modules/graph/graph_ingestor.py) explicitly calculates approximate counts by summing the lengths of extracted entity lists for each procedure; [the uploader](../bulk_upload_pdfs.py) then sums those values across uploads. Neo4j `MERGE` can reuse existing records. The counter also includes entity categories that the insertion mapping does not use. These are approximate construction counters, not measurements of the final database's unique contents. The initial/final graph statistics recorded in that summary are zero and cannot establish the deleted database's size.

This finding explains why matching the manuscript's numbers is not a valid reconstruction target. It does not prove the size of the deleted database. The February replay itself produced approximate counters of 487/442 and 92/272 unique records. The full replay produced approximate counters of 739/666 and 115/382 unique records. Neither replay reproduces the old counters exactly.

## Reconstruction method and boundaries

- Read the existing trusted `backend/faiss_index.index.meta.npy.backup`: 2,486 rows, 21 source names and 28 contiguous ingestion runs. No PDFs were re-ingested.
- Matched the February successful uploads by filename, chunk count and terminal vector count. For the full rebuild, selected every declared-complete saved source/text sequence, preserving original row order and source aliases. Repeated runs of the same source/text were collapsed; alternate chunking runs remain in the provenance.
- Reassembled saved chunks with their recorded zero-overlap, 400- or 500-word chunking. Both chunkings of `1.pdf` produce the same normalized full text. Chunk joining cannot recover PDF layout, original whitespace or all original NLP sentence boundaries.
- Excluded an incomplete WHO attempt (84 of 201 chunks) and the failed textbook upload (360 of 1,199 chunks). A complete WHO run was available and included. Partial textbook text was not presented as a complete document.
- Used `en_core_sci_md` 0.5.4 with spaCy 3.7.5 in an isolated environment, following the current repository's model requirement. The original runtime version is unknown. The [SciSpacy 0.5.4 release](https://github.com/allenai/scispacy/releases/tag/v0.5.4) documents its spaCy 3.7 migration. The full environment freeze and model file hashes are retained.
- Replayed the existing extractor and the original top-five-procedure/context construction methods, including their label/name merge and directed relationship semantics. Exact-input NLP parsing was memoized within each document. Dependency relations are computed by the old code but never inserted; that behavior was preserved.
- Recorded construction-document IDs on nodes and relationships and retained input/code/model hashes and per-document traces. These IDs resolve to saved-text inputs; they are not recovered historical citations or human judgments. The generic inventory does not recognize this custom provenance field and therefore flags missing direct source-reference fields.
- Did not use benchmark answers, add invented clinical relationships, adjust counts to a target, or call an LLM API for this reconstruction. `human_validated` and `submission_graph_identity_confirmed` remain false.

The source snapshot preserves the original construction code; raw output folders are local research records. The live database's internal IDs and timestamps are new. Original image-derived records and undocumented edits cannot be reconstructed from the saved text.

## Artifacts and validation

- [Rebuilt Neo4j dump](../revision_outputs/rebuilt_local_neo4j_20260926/dump/neo4j.dump): a stopped-database export created before serving the new local copy; 75,606 bytes.
- [Full reconstructed snapshot](../revision_outputs/rebuilt_full_corpus_20260926/graph_snapshot.json), [summary](../revision_outputs/rebuilt_full_corpus_20260926/rebuild_summary.json), [inventory](../revision_outputs/rebuilt_full_corpus_20260926/graph_inventory.md), and [per-document replay](../revision_outputs/rebuilt_full_corpus_20260926/document_replay.json).
- [Input selection audit](../revision_outputs/rebuild_inputs_20260926/rebuild_input_audit.json), [reconstructed text inputs](../revision_outputs/rebuild_inputs_20260926/full_recovered_documents.jsonl), and [input manifest](../revision_outputs/rebuilt_full_corpus_20260926/input_manifest.json).
- [February replay summary](../revision_outputs/rebuilt_february_batch_20260926/rebuild_summary.json), retained separately for comparison with the old upload report.
- [Import validation](../revision_outputs/rebuilt_local_neo4j_20260926/validation.json) and [import manifest](../revision_outputs/rebuilt_local_neo4j_20260926/import_manifest.json): every node label/property and relationship type/endpoint/property was read back and compared with the input snapshot before creating the dump. Nested JSON metadata is stored losslessly alongside native Neo4j fields.
- [Local connection check](../revision_outputs/rebuilt_connection_check_20260926/preflight.json): read-only export made while `backend/.env` still selected the local service; 115 nodes and 382 relationships.
- [Aura deployment record](AURA_DEPLOYMENT.md) and locally retained, Git-ignored import and connection-check artifacts: exact hosted copy of the same snapshot, now selected by `backend/.env`.
- [Python environment freeze](../revision_outputs/rebuild_env_20260926/requirements.freeze.txt). Exact model, input, output and construction-code hashes are recorded in the snapshot and manifests.

Dump SHA-256: `a9fa77fa8f287b8302086cf4a56369d65455f0b9de08667f599bf9bd3824632f`.

Full reconstructed semantic graph SHA-256: `d97e0e1b09fdefb056e344a3e7d689bf3bce8b7fb85c3416ac2531d22cd2e3e0`.

All **137 revision tests passed**, covering the existing evaluation code plus saved-input selection, original-constructor replay, local and Aura import fidelity, overwrite guards, and connection-setting preservation. A separate synthetic import also exercised nested/mixed properties and authenticated service startup/shutdown. These checks establish software/data consistency; they do not establish clinical correctness.

## Using the preserved local database

The local service uses the installed Neo4j Enterprise 2025.12.1 distribution and cached JDK 21. When started, it runs as a hidden, authenticated, loopback-only process independently of the existing Desktop instance. Connection: `bolt://127.0.0.1:7688`; database/user: `neo4j`. Its generated password remains in the ignored `connection.private.json` inside its database folder. `backend/.env` currently selects Aura, so the local credential is no longer stored there. Keep all credential files private.

The helper does not serve an HTTP Neo4j Browser and is not automatically registered as a Desktop-managed instance. A Neo4j client can connect to the Bolt endpoint while it is running; the dump can also be imported into a separate compatible instance.

Run from the repository root:

```powershell
python -m backend.evaluation.revision.local_graph status --home backend/evaluation/revision_outputs/rebuilt_local_neo4j_20260926
python -m backend.evaluation.revision.local_graph stop --home backend/evaluation/revision_outputs/rebuilt_local_neo4j_20260926
```

The service currently reports `running: false`. To use it instead of Aura, restart it with:

```powershell
python -m backend.evaluation.revision.local_graph start --home backend/evaluation/revision_outputs/rebuilt_local_neo4j_20260926 --port 7688
```

This leaves `backend/.env` pointing to Aura. Add `--configure-env` only when deliberately switching the backend back to the local copy, then restart the backend process. The service does not automatically start after a computer restart. The dump contains the `neo4j` graph database; its authentication credentials belong to this separate local service, not to the dump. Set credentials on any new destination instance when importing it.

For future reconstructions, choose fresh output paths. First run `prepare_rebuild_inputs`, then `rebuild_legacy_graph` in the saved model environment, then `import_snapshot` with the local Neo4j/JDK paths. Each tool exposes `--help` and refuses to overwrite completed outputs.

## What this changes for the revision

The reconstruction restores a usable local graph and creates a reproducible basis for new work. The previous 60-question diagnostic and its one-repair development variant were subsequently rerun against this graph with the same frozen evidence and exact archived model responses. [The comparison](REBUILT_GRAPH_EXPERIMENT_COMPARISON.md) found no operational changes: both graph arms still answered 0/60 because every checked relation remained unknown through unresolved entities. No improvement in accuracy, hallucination rate or clinical quality is established by this rebuild.

Next, review the constructed relationships against source passages, resolve entity/predicate coverage problems, and freeze the resulting version before running and labeling new comparisons. Temporal and contraindication claims still require actual source-supported construction and validation. Any paper revision should report measured unique database counts and describe the newly reconstructed graph accurately.
