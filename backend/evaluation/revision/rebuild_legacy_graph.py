"""Offline semantic replay of the surviving legacy graph constructor.

Requires an explicitly approved document JSONL and an explicitly selected installed
spaCy model. Never imports app settings, opens Neo4j, downloads models, adds clinical
rules, or adjusts counts to manuscript targets. Original whitespace, database IDs,
timestamps, curation, and deleted database contents are not recovered.
"""
from __future__ import annotations

import argparse
import ast
import copy
from collections import Counter
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Dict, List


BACKEND = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = BACKEND / "modules/graph/entity_extractor.py"
INGESTOR_PATH = BACKEND / "modules/graph/graph_ingestor.py"
MANAGER_PATH = BACKEND / "modules/graph/neo4j_manager.py"
CHUNKER_PATH = BACKEND / "modules/data_ingestion/chunker.py"


class ReconstructionError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def reconstruct_normalized_text(chunks, *, chunk_words, overlap_words):
    """Reassemble a declared chunking scheme exactly at the whitespace-token level.

    This cannot restore the original full text's whitespace or sentence boundaries.
    No longest-overlap heuristic or implicit choice between conflicting uploads.
    """
    if type(chunk_words) is not int or chunk_words < 1 or type(overlap_words) is not int or not 0 <= overlap_words < chunk_words:
        raise ReconstructionError("Explicit valid chunk_words/overlap_words are required")
    if not isinstance(chunks, list) or not chunks:
        raise ReconstructionError("A nonempty selected chunk sequence is required")
    indexed = {}
    for chunk in chunks:
        if not isinstance(chunk, dict) or type(chunk.get("chunk_index")) is not int or chunk["chunk_index"] < 0:
            raise ReconstructionError("Chunk indices must be nonnegative integers")
        if not isinstance(chunk.get("text"), str) or not chunk["text"].strip():
            raise ReconstructionError("Every selected chunk requires nonempty text")
        words = chunk["text"].split()
        index = chunk["chunk_index"]
        if index in indexed and indexed[index] != words:
            raise ReconstructionError(f"Conflicting text versions for chunk index {index}")
        indexed[index] = words
    if sorted(indexed) != list(range(len(indexed))):
        raise ReconstructionError("Selected chunks must be complete contiguous indices starting at zero")
    sequences = [indexed[index] for index in range(len(indexed))]
    if any(len(words) != chunk_words for words in sequences[:-1]) or not 1 <= len(sequences[-1]) <= chunk_words:
        raise ReconstructionError("Chunk lengths do not match the declared chunking scheme")
    words = list(sequences[0])
    for sequence in sequences[1:]:
        if overlap_words and (len(sequence) <= overlap_words or words[-overlap_words:] != sequence[:overlap_words]):
            raise ReconstructionError("Declared token overlap does not match exactly or adds no new text")
        words.extend(sequence[overlap_words:])
    roundtrip = []
    start = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        roundtrip.append(words[start:end])
        if end == len(words):
            break
        start = end - overlap_words
    if roundtrip != sequences:
        raise ReconstructionError("Reassembled text does not round-trip to the selected chunks")
    return " ".join(words)


def validate_documents(documents):
    if not isinstance(documents, list) or not documents:
        raise ReconstructionError("At least one explicitly selected document is required")
    seen, output = set(), []
    for document in documents:
        if not isinstance(document, dict):
            raise ReconstructionError("Every document must be an object")
        for key in ("document_id", "source", "text"):
            if not isinstance(document.get(key), str) or not document[key].strip():
                raise ReconstructionError(f"Document requires nonempty {key}")
        if document["document_id"] in seen:
            raise ReconstructionError("Duplicate document_id; source aliases need distinct explicit document IDs")
        seen.add(document["document_id"])
        provenance = document.get("provenance")
        if not isinstance(provenance, dict) or not isinstance(provenance.get("assembly"), dict):
            raise ReconstructionError("Document provenance must declare its assembly parameters")
        if provenance.get("ambiguous", False):
            raise ReconstructionError("Ambiguous input selection must be resolved before reconstruction")
        assembly = provenance["assembly"]
        assembled = reconstruct_normalized_text(document.get("chunks"), chunk_words=assembly.get("chunk_words"),
                                                overlap_words=assembly.get("overlap_words"))
        if document["text"] != assembled:
            raise ReconstructionError("Supplied text must exactly equal the declared normalized chunk reconstruction")
        text_hash = hashlib.sha256(assembled.encode("utf-8")).hexdigest()
        for claimed_hash in (document.get("text_sha256"), provenance.get("text_sha256")):
            if claimed_hash is not None and claimed_hash != text_hash:
                raise ReconstructionError("Document text checksum mismatch")
        selected = copy.deepcopy(document)
        selected["text_sha256"] = text_hash
        selected["original_whitespace_recovered"] = False
        output.append(selected)
    return output


class CaptureLogger:
    def __init__(self):
        self.events = []

    def _record(self, level, message, *args, **kwargs):
        self.events.append({"level": level, "message": str(message) % args if args else str(message)})

    def info(self, message, *args, **kwargs):
        self._record("info", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._record("warning", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._record("error", message, *args, **kwargs)


def load_legacy_method(path, class_name, method_name, logger):
    """Execute only the named trusted repository method, avoiding module imports."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    method = next((item for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
                   for item in node.body if isinstance(item, ast.FunctionDef) and item.name == method_name), None)
    if method is None:
        raise ReconstructionError(f"Required legacy method missing: {class_name}.{method_name}")
    module = ast.Module(body=[copy.deepcopy(method)], type_ignores=[])
    scope = {"Dict": Dict, "List": List, "Any": Any, "logger": logger}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), scope)
    return scope[method_name]


class SemanticGraphSink:
    """Reproduce Neo4j MERGE-by-(label,name) semantics without any database."""
    def __init__(self, legacy_add_method):
        self.nodes, self.edges = {}, {}
        self.document_id = None
        self.add_procedure_with_entities = MethodType(legacy_add_method, self)

    def _node(self, label, name, description=None):
        if not isinstance(name, str) or not name.strip():
            raise ReconstructionError("Legacy extractor produced an invalid node name")
        key = (label, name)
        if key not in self.nodes:
            self.nodes[key] = {"id": "rebuild-node-" + digest(key), "label": label, "name": name,
                               "description": description, "documents": set()}
        elif description:
            self.nodes[key]["description"] = description
        self.nodes[key]["documents"].add(self.document_id)
        return self.nodes[key]["id"]

    def create_procedure_node(self, name, description="", metadata=None):
        return self._node("Procedure", name, description)

    def create_entity_node(self, entity_type, name, properties=None):
        return self._node(entity_type, name)

    def create_relationship(self, from_node, to_node, relationship_type, from_label, to_label, properties=None):
        source_key, target_key = (from_label, from_node), (to_label, to_node)
        if source_key not in self.nodes or target_key not in self.nodes:
            return False
        key = (source_key, relationship_type, target_key)
        self.edges.setdefault(key, set()).add(self.document_id)
        return True

    def snapshot(self):
        nodes = []
        for key, node in sorted(self.nodes.items()):
            props = {"name": node["name"], "reconstruction_document_ids": sorted(node["documents"])}
            if node["description"] is not None:
                props["description"] = node["description"]
            nodes.append({"id": node["id"], "labels": [node["label"]], "properties": props})
        edges = [{"id": "rebuild-edge-" + digest(key), "source": self.nodes[key[0]]["id"], "type": key[1],
                  "target": self.nodes[key[2]]["id"], "properties": {"reconstruction_document_ids": sorted(documents),
                  "construction_rule": "legacy_procedure_context_entity_cooccurrence", "human_validated": False}}
                 for key, documents in sorted(self.edges.items())]
        return {"nodes": nodes, "edges": edges}


class TracedExtractor:
    def __init__(self, extractor):
        self.extractor, self.calls = extractor, []

    def extract_entities(self, text):
        result = self.extractor.extract_entities(text)
        self.calls.append({"method": "extract_entities", "entities": copy.deepcopy(result)})
        return result

    def identify_main_procedures(self, text, top_n=3):
        result = self.extractor.identify_main_procedures(text, top_n=top_n)
        self.calls.append({"method": "identify_main_procedures", "top_n": top_n, "procedures": copy.deepcopy(result)})
        return result

    def extract_procedure_specific_entities(self, text, procedure):
        result = self.extractor.extract_procedure_specific_entities(text, procedure)
        self.calls.append({"method": "extract_procedure_specific_entities", "procedure": procedure, "entities": copy.deepcopy(result)})
        return result

    def extract_relationships(self, text):
        result = self.extractor.extract_relationships(text)
        self.calls.append({"method": "extract_relationships", "returned_count": len(result), "inserted_by_legacy_method": False})
        return result


class DocumentNlpCache:
    """Cache read-only spaCy Docs by exact input string within one document replay."""
    def __init__(self, pipeline):
        self.pipeline, self.cache = pipeline, {}
        self.hits, self.misses = 0, 0

    def __getattr__(self, name):
        return getattr(self.pipeline, name)

    def __call__(self, text, *args, **kwargs):
        if args or kwargs or not isinstance(text, str):
            return self.pipeline(text, *args, **kwargs)
        if text in self.cache:
            self.hits += 1
            return self.cache[text]
        self.misses += 1
        self.cache[text] = self.pipeline(text)
        return self.cache[text]

    def statistics(self):
        return {"enabled": True, "exact_text_cache_hits": self.hits, "pipeline_calls": self.misses,
                "distinct_cached_texts": len(self.cache), "cleared_after_document": True}


def replay_documents(documents, extractor, *, progress=None):
    """Replay original methods; expose approximate legacy counters separately."""
    documents = validate_documents(documents)
    logger = CaptureLogger()
    add = load_legacy_method(MANAGER_PATH, "Neo4jManager", "add_procedure_with_entities", logger)
    build = load_legacy_method(INGESTOR_PATH, "GraphEnhancedIngestor", "_build_graph_from_text", logger)
    sink = SemanticGraphSink(add)
    report = []
    for position, document in enumerate(documents, 1):
        if progress:
            progress({"event": "document_started", "position": position, "total": len(documents),
                      "document_id": document["document_id"], "source": document["source"], "characters": len(document["text"])})
        start_events = len(logger.events)
        traced = TracedExtractor(extractor)
        session = SimpleNamespace(extractor=traced, graph=sink)
        sink.document_id = document["document_id"]
        original_nlp = getattr(extractor, "nlp", None)
        cache = DocumentNlpCache(original_nlp) if original_nlp is not None else None
        if cache:
            extractor.nlp = cache
        try:
            stats = build(session, document["text"], document["source"])
        finally:
            if cache:
                extractor.nlp = original_nlp
        cache_stats = cache.statistics() if cache else {"enabled": False, "reason": "extractor_has_no_nlp_pipeline"}
        if cache:
            cache.cache.clear()
        events = logger.events[start_events:]
        if any(event["level"] == "error" for event in events):
            # The legacy method swallows exceptions; a reconstruction must not
            # turn partially inserted nodes into a successfully rebuilt graph.
            raise ReconstructionError(f"Legacy constructor logged an error for document {document['document_id']}")
        report.append({"document_id": document["document_id"], "source": document["source"],
                       "text_sha256": document["text_sha256"], "legacy_approximate_stats": stats,
                       "extractor_trace": traced.calls, "legacy_log": events, "nlp_memoization": cache_stats,
                       "cumulative_unique_nodes": len(sink.nodes), "cumulative_unique_edges": len(sink.edges)})
        if progress:
            progress({"event": "document_completed", "position": position, "total": len(documents),
                      "document_id": document["document_id"], "legacy_approximate_stats": stats,
                      "unique_nodes_so_far": len(sink.nodes), "unique_edges_so_far": len(sink.edges),
                      "nlp_memoization": cache_stats})
    snapshot = sink.snapshot()
    semantic = {"nodes": sorted([list(key) for key in sink.nodes]),
                "edges": sorted([[*key[0], key[1], *key[2]] for key in sink.edges])}
    summary = {"documents_replayed": len(documents), "unique_document_texts": len({d["text_sha256"] for d in documents}),
               "unique_nodes": len(snapshot["nodes"]), "unique_edges": len(snapshot["edges"]),
               "relation_type_counts": dict(sorted(Counter(edge["type"] for edge in snapshot["edges"]).items())),
               "legacy_approximate_totals": {name: sum(item["legacy_approximate_stats"].get(name, 0) for item in report)
                    for name in ("entities_extracted", "graph_nodes_created", "graph_relationships_created")},
               "legacy_approximate_totals_are_not_unique_graph_counts": True,
               "semantic_graph_sha256": digest(semantic), "submission_graph_identity_confirmed": False}
    return snapshot, summary, report, documents


def load_extractor(model_name):
    """Load the existing extractor directly, avoiding graph package/app imports."""
    spec = importlib.util.spec_from_file_location("revision_legacy_entity_extractor", EXTRACTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MedicalEntityExtractor(model_name=model_name)


def model_provenance(extractor, requested_model):
    nlp = extractor.nlp
    meta = getattr(nlp, "meta", {})
    model_dir = getattr(nlp, "path", None)
    files = []
    if model_dir is not None and Path(model_dir).is_dir():
        for path in sorted(Path(model_dir).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files.append({"relative_path": path.relative_to(model_dir).as_posix(), "sha256": file_hash(path), "bytes": path.stat().st_size})
    return {"requested_model": requested_model, "spacy_version": importlib.metadata.version("spacy"),
            "model_meta": {key: meta.get(key) for key in ("lang", "name", "version", "spacy_version", "pipeline")},
            "model_files": files, "model_files_sha256": digest(files) if files else None,
            "historical_runtime_model_version_confirmed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", required=True, type=Path, help="Approved source/document_id/text/chunks/provenance JSONL")
    parser.add_argument("--model", required=True, help="Explicit locally installed spaCy model; no fallback/download")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Choose a new empty output directory; existing graph artifacts are never overwritten")
    documents = [json.loads(line) for line in args.documents.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    documents = validate_documents(documents)  # Fail ambiguity before loading any model.
    code = {path.name: file_hash(path) for path in (EXTRACTOR_PATH, INGESTOR_PATH, MANAGER_PATH, CHUNKER_PATH, Path(__file__))}
    print(json.dumps({"event": "loading_local_model", "model": args.model}), flush=True)
    extractor = load_extractor(args.model)
    model = model_provenance(extractor, args.model)
    snapshot, summary, per_document, validated = replay_documents(documents, extractor,
        progress=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
    snapshot["provenance"] = {"kind": "legacy_code_reconstruction_not_deleted_database_recovery",
        "submission_graph_identity_confirmed": False, "documents_sha256": file_hash(args.documents),
        "code_sha256": code, "model": model, "semantic_graph_sha256": summary["semantic_graph_sha256"],
        "original_whitespace_recovered": False, "original_database_ids_or_timestamps_recovered": False,
        "manual_curation_recovered": False, "human_validated": False,
        "execution_optimization": "Exact-input-string spaCy Doc memoization within one document; original extractor methods only read Docs; cache cleared after every document",
        "construction_semantics": "Original top-five procedure/context entity constructor; dependency relationships computed but never inserted"}
    summary["limitations"] = ["Reconstructed normalized text does not recover original whitespace or original NLP sentence boundaries.",
        "Counts are measured outputs, not adjusted to a manuscript target.",
        "The original constructor creates entity-cooccurrence edges, not independently validated clinical assertions.",
        "Original database contents, manual edits, timestamps, identities and model runtime remain unconfirmed."]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"graph_snapshot.json": snapshot, "rebuild_summary.json": summary,
               "document_replay.json": per_document,
               "input_manifest.json": [{key: value for key, value in doc.items() if key not in ("text", "chunks")} |
                    {"chunks": [{key: value for key, value in chunk.items() if key != "text"} |
                                 {"text_sha256": hashlib.sha256(chunk["text"].encode()).hexdigest()} for chunk in doc["chunks"]]}
                    for doc in validated]}
    for filename, value in outputs.items():
        (args.output_dir / filename).write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot_dir = args.output_dir / "source_snapshot"
    snapshot_dir.mkdir()
    for source_path in (EXTRACTOR_PATH, INGESTOR_PATH, MANAGER_PATH, CHUNKER_PATH, Path(__file__)):
        (snapshot_dir / source_path.name).write_bytes(source_path.read_bytes())
    artifact_hashes = {filename: file_hash(args.output_dir / filename) for filename in outputs}
    (args.output_dir / "artifact_sha256.json").write_text(json.dumps(artifact_hashes, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
