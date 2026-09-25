# Frozen graph verification

`graph_verifier.py` is a deterministic offline checker. It does not construct a
graph, extract relations, call a model, or establish clinical completeness.

Snapshots are JSON objects containing `nodes` and `edges` lists:

```json
{
  "nodes": [
    {"id": "step-a", "labels": ["Step"], "properties": {"name": "Expose triangle", "aliases": ["Exposure"]}},
    {"id": "step-b", "labels": ["Step"], "properties": {"name": "Clip duct"}}
  ],
  "edges": [
    {"source": "step-a", "target": "step-b", "type": "PRECEDES", "properties": {"source_document": "guideline-id", "source_quote": "Original source passage"}}
  ]
}
```

IDs must be unique nonempty strings; edge endpoints must be existing IDs. Labels
do not restrict which predicates a node may participate in. All edge properties
are preserved in verification traces. Snapshot SHA-256 is computed from UTF-8
JSON with sorted object keys, compact separators, and unescaped Unicode; array
order remains significant. This is a content checksum, not necessarily the hash
of the original JSON file bytes.

Expected claims contain `source`, `relation`, `target`, `evidence_quote`, and
`chunk_id`, all nonempty strings, plus optional boolean `required` (default true).
The caller must validate that the quote occurs in the candidate and induces the
assertion; a graph match alone does not establish textual entailment.

Exact, case-sensitive node IDs take precedence over names. Otherwise the checker
uses exact name/alias matching after case folding and whitespace normalization.
Names are `properties.name`; aliases are `properties.aliases`, a list of strings.
Multiple matching nodes produce unknown, never an arbitrary choice. No fuzzy
matching or clinical synonym expansion is performed.

Predicate tokens remain case-sensitive and otherwise unchanged. The only
equivalence is `A FOLLOWS B` = `B PRECEDES A`, applied consistently to graph edges
and expected claims. `A PRECEDES B` contradicts `B PRECEDES A`; no transitive
closure, temporal inference, or procedure-context inference is performed.
`CONTRAINDICATES` and `ALLOWS` are explicit same-endpoint opposing predicates by
default. Extra same-endpoint opposing predicate pairs may be declared through
`FrozenGraph(..., opposite_relations=[...])`; this argument replaces the default
list and its contents must be recorded in the experiment configuration. Legacy
names such as `CONTRAINDICATED_WITH` are not equated with `CONTRAINDICATES` or
interpreted as symmetric without a separately justified, recorded preprocessing
step. Any other exact typed edge can support its identical expected assertion;
absence of an edge is unknown, not contradiction.

An exact support and an explicit opposite together produce state `contradicted`
with `conflict=true`. Graph conflicts always veto, even when the optional
soft-only policy disables the required-contradiction veto. This makes three-state
counts exhaustive without hiding graph inconsistency. A temporal self-loop is
its own opposite and therefore a conflict.

Repeated canonical assertions within the same chunk count once. All input claim
records remain in `provenance`, and `required` is true if any duplicate requires
the relation. Support is supported / (supported + contradicted); relation
coverage is (supported + contradicted) / expected relations. Support is null when
there are no known relations. Empty expected relations cannot certify a chunk.
Default pilot thresholds are support = 1.0 and coverage = 1.0; alternate thresholds
must be selected on development data and frozen before evaluation. This support
score has no probabilistic calibration claim.

`gate_chunks(graph, chunks, claims_by_chunk, ...)` requires unique `chunk_id`
values and rejects mismatched claim IDs. It returns retained/rejected chunks and
every chunk report. Only `retained_chunks` should be passed to the answer
generator, with the relevant traces. Query eligibility means at least one chunk
passes the prespecified policy; a contradiction in a rejected chunk does not
globally veto every other candidate. Neither eligibility nor an exact graph
match proves answer completeness, clinical safety, or absence of generation
errors. Query-level answering and final response assessment remain separate.
