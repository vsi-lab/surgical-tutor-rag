# Restore a dump for revision diagnostics

The supplied `neo4j-2026-09-25T05-49-24.dump` was sufficient to recover a graph without the running Desktop instance's password. The original instance was not modified. A database dump restores data; it does not establish that the graph is the version used for the submitted study.

Input SHA-256: `c131de1649c761e2b5528b5470b3380f8cea0ab1f69d9d4b4287c669e67a802e`.

The first restoration used the locally installed Neo4j Enterprise 2025.12.1 libraries and Zulu Java 21.0.8. A subsequent independent restoration using the wrapper below reproduced all 49 node label/property records and 66 typed relationship/property records. Neo4j creates a different database UUID on a fresh restoration, so element IDs, timestamps and snapshot file hashes can differ between exports. The experiment uses the preserved first snapshot's exact checksum.

Run from the repository root. Choose a new output directory each time:

```powershell
python -m backend.evaluation.revision.export_dump --dump "C:\Users\smang\Downloads\neo4j-2026-09-25T05-49-24.dump" --neo4j-home "C:\Users\smang\.Neo4jDesktop2\Cache\dbmss\neo4j-enterprise-2025.12.1" --java-home "C:\Users\smang\.Neo4jDesktop2\Cache\runtime\zulu21.44.17-ca-jdk21.0.8-win_x64" --output-dir backend/evaluation/revision_outputs/new_dump_restore
```

The wrapper copies the input, loads it with `org.neo4j.cli.AdminTool`, compiles `DumpGraphExport.java`, then opens only the workspace copy through Neo4j's embedded API. Client Bolt/HTTP/HTTPS connectors and online backup are disabled; internal cluster listeners use temporary loopback ports. The Java service shuts down after export. No original-instance credentials are read or required.

Outputs include `graph_snapshot.json`, `restore_manifest.json` with software/input/source hashes, and stdout/stderr files for each step. The output directory must be a nonexistent child of this repository; the script does not delete, overwrite or clean up existing database directories. If a step fails, inspect its logs and choose another fresh directory after resolving the cause. The Java exporter additionally requires an isolated-copy marker and refuses to overwrite a snapshot.

The first measured snapshot and audit are under `backend/evaluation/revision_outputs/dump_restore_20260925/`. The independent wrapper check is under `backend/evaluation/revision_outputs/dump_restore_reproduction_20260925/`. These generated files are ignored by Git and should be preserved with the research records.

Neo4j's documented restore operation is [database load](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/). The helper uses the specific installed version above; a different dump version or storage format can require a matching Neo4j distribution.
