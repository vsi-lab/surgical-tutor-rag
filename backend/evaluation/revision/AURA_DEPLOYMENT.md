# Aura deployment of the reconstructed graph

Completed on 26 September 2026 America/Phoenix (27 September UTC). The configured Neo4j Aura database is now the backend's active graph database. `backend/.env` points to the Aura connection using values read from the downloaded credential file. The Aura username, URI, and password remain only in local ignored credential files; they were not written to tracked source or this report. Restart an already-running backend process so it reloads the changed environment file.

This deployment is a hosted copy of the graph reconstructed from surviving saved text chunks. It is not a recovery of the deleted database used for the submitted paper, and it does not make the submitted graph-dependent results reproducible.

## Imported graph

The target database was empty before import. The importer created the complete snapshot in one explicit transaction and then performed lossless record-level readback. The deployed graph contains **115 nodes and 382 directed relationships**.

| Node label | Count |
|---|---:|
| Anatomy | 27 |
| Complication | 16 |
| Instrument | 11 |
| Medication | 18 |
| Procedure | 23 |
| Technique | 20 |

| Relationship type | Count |
|---|---:|
| `INVOLVES` | 140 |
| `MAY_CAUSE` | 62 |
| `REQUIRES` | 18 |
| `REQUIRES_MEDICATION` | 48 |
| `USES_TECHNIQUE` | 114 |

Snapshot file SHA-256: `05efde547935d0d2079f42e90f9d1bcc04c834adec2ac8e6d68160c3b4341027`.

Application-visible semantic graph SHA-256: `d97e0e1b09fdefb056e344a3e7d689bf3bce8b7fb85c3416ac2531d22cd2e3e0`.

## Validation and safeguards

- The import refused a nonempty target unless its complete preserved record set already matched the source snapshot.
- Labels and relationship types had to pass a strict Cypher-identifier pattern before interpolation; all data values were parameterized.
- One explicit transaction created all records, with automatic transaction retry disabled to avoid duplicate creation after an ambiguous commit response.
- Every node's labels and properties and every relationship's type, direction, endpoints, and properties matched the source snapshot after readback.
- All 23 procedure-context queries matched the snapshot-derived expected results.
- Six label-specific `name` indexes are `ONLINE`: `anatomy_name`, `complication_name`, `instrument_name`, `medication_name`, `procedure_name`, and `technique_name`.
- A second read-only export through the normal `backend/.env` configuration reported 115 nodes, 382 relationships, and the expected relationship-type counts.
- Direct connection through the application's `Neo4jManager` succeeded and reported 23 procedures.
- The importer exposes no database delete or clear operation. Re-running it against this exact deployment validates and exits without adding records.

The locally retained, Git-ignored Aura import manifest records target identity, pre-import counts, aggregate counts, index states, and validation status. A separate ignored connection preflight and graph snapshot record the application-configured readback. The import implementation is [aura_import.py](aura_import.py), with focused coverage in [test_revision_aura_import.py](../../../tests/test_revision_aura_import.py).

All **137 revision tests passed** after adding the Aura importer and its safety tests. These checks establish deployment fidelity and software behavior; they do not establish clinical correctness or identity with the deleted submission graph.

## Local fallback

The reconstructed local database, its dump, and its generated authentication file remain preserved under `backend/evaluation/revision_outputs/rebuilt_local_neo4j_20260926`. Its hidden Neo4j service was stopped gracefully after Aura validation and reports `running: false`. The original Neo4j Desktop data and the supplied 49-node/66-relationship dump also remain unchanged.

The previous local Neo4j environment values were saved privately under the ignored Aura import artifact directory before `backend/.env` was updated. Use [LOCAL_GRAPH_REBUILD.md](LOCAL_GRAPH_REBUILD.md) if the local fallback must be started again; starting it with `--configure-env` will intentionally replace the active Aura settings.
