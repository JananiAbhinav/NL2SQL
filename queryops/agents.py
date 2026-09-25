from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import Catalog, SchemaObject
from .retrieval import HybridRetriever


@dataclass
class TestCase:
    name: str
    category: str
    rationale: str
    validation_sql_hint: str
    objects: list[str]


class TestcaseAgent:
    """Deterministic test planning from structural metadata and retrieved logic context."""
    def __init__(self, catalog: Catalog, retriever: HybridRetriever):
        self.catalog, self.retriever = catalog, retriever

    def generate(self, object_name: str) -> list[TestCase]:
        obj = self.catalog.get(object_name)
        if not obj:
            raise KeyError(f"Unknown catalog object: {object_name}")
        context = self.retriever.retrieve(f"{obj.name} {obj.description} {obj.logic_summary}", top_k=5)
        names = list(dict.fromkeys([obj.name] + [h.object.name for h in context]))
        cases = [TestCase("row_count_non_negative", "completeness", "Confirm the object can be queried and has no negative row count.",
                          f"SELECT COUNT(*) FROM {obj.qualified_name}", names)]
        for column in obj.columns:
            qualified = f"{obj.qualified_name}.{column.name}"
            if not column.nullable:
                cases.append(TestCase(f"{column.name}_not_null", "completeness", "Column metadata marks this field non-null.",
                                      f"SELECT COUNT(*) FROM {obj.qualified_name} WHERE {column.name} IS NULL", names))
            if any(t in column.data_type.casefold() for t in ("int", "decimal", "numeric", "float", "double")):
                cases.append(TestCase(f"{column.name}_numeric_validity", "validity", "Check numeric values and boundary distributions.",
                                      f"SELECT MIN({column.name}), MAX({column.name}) FROM {obj.qualified_name}", names))
        for rel in self.catalog.relationships:
            if rel.left_object == obj.name or rel.right_object == obj.name:
                own_col = rel.left_column if rel.left_object == obj.name else rel.right_column
                peer_obj = rel.right_object if rel.left_object == obj.name else rel.left_object
                peer_col = rel.right_column if rel.left_object == obj.name else rel.left_column
                cases.append(TestCase(f"{own_col}_referential_integrity", "referential", "Check declared relationship coverage.",
                                      f"SELECT COUNT(*) FROM {obj.qualified_name} s LEFT JOIN {peer_obj} p ON s.{own_col}=p.{peer_col} WHERE p.{peer_col} IS NULL", names))
        if obj.logic_summary:
            cases.append(TestCase("transformation_logic_review", "business_rule", obj.logic_summary,
                                  f"-- Derive assertion from transformation logic for {obj.qualified_name}", names))
        return cases


class DataComparisonAgent:
    """Generate portable set-difference SQL and bucket summaries for large comparisons."""
    def align_columns(self, source: SchemaObject, target: SchemaObject) -> list[str]:
        target_names = {c.name.casefold() for c in target.columns}
        return [c.name for c in source.columns if c.name.casefold() in target_names]

    def difference_sql(self, source: str, target: str, columns: list[str], dialect: str = "ansi") -> str:
        if not columns:
            raise ValueError("No shared columns are available for comparison")
        projection = ", ".join(columns)
        return (f"SELECT {projection} FROM {source} EXCEPT SELECT {projection} FROM {target};\n"
                f"SELECT {projection} FROM {target} EXCEPT SELECT {projection} FROM {source}")

    @staticmethod
    def bucket_key(values: tuple[Any, ...], bucket_count: int = 256) -> int:
        if bucket_count < 1:
            raise ValueError("bucket_count must be positive")
        import hashlib, json
        payload = json.dumps(values, sort_keys=True, default=str, separators=(",", ":")).encode()
        return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % bucket_count

    @classmethod
    def bucket_hashes(cls, rows: list[tuple[Any, ...]], bucket_count: int = 256) -> dict[int, str]:
        import hashlib, json
        buckets: dict[int, list[str]] = {}
        for row in rows:
            key = cls.bucket_key(row, bucket_count)
            buckets.setdefault(key, []).append(json.dumps(row, sort_keys=True, default=str, separators=(",", ":")))
        return {key: hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()
                for key, values in buckets.items()}

    @staticmethod
    def mismatched_buckets(left: dict[int, str], right: dict[int, str]) -> list[int]:
        return sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))


class IncidentRCAAgent:
    """Assemble a compact, evidence-first incident packet for an LLM or human investigator."""
    def __init__(self, catalog: Catalog, retriever: HybridRetriever, incidents: list[dict[str, Any]] | None = None):
        self.catalog, self.retriever = catalog, retriever
        self.incidents = incidents or []

    def investigate(self, incident: str, top_k: int = 5) -> dict[str, Any]:
        hits = self.retriever.retrieve(incident, top_k=top_k, lineage_depth=2)
        terms = set(incident.casefold().split())
        similar = []
        for item in self.incidents:
            text = " ".join(str(item.get(k, "")) for k in ("title", "description", "resolution")).casefold()
            score = len(terms & set(text.split())) / max(len(terms), 1)
            if score:
                similar.append((score, item))
        similar.sort(key=lambda x: x[0], reverse=True)
        return {"incident": incident,
                "likely_objects": [h.object.qualified_name for h in hits],
                "lineage": [asdict(edge) for edge in self.catalog.lineage
                            if edge.upstream in {h.object.name for h in hits} or edge.downstream in {h.object.name for h in hits}],
                "logic": {h.object.qualified_name: h.object.logic_summary for h in hits if h.object.logic_summary},
                "similar_incidents": [item for _, item in similar[:top_k]],
                "evidence_gaps": ["Validate the affected time window and recent deployment changes.",
                                  "Confirm suspected cause against source-system and execution logs."]}
