from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str = "unknown"
    nullable: bool = True
    description: str = ""
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaObject:
    name: str
    columns: tuple[Column, ...]
    description: str = ""
    schema: str = "default"
    object_type: str = "table"
    logic_summary: str = ""
    grain: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"

    def searchable_text(self) -> str:
        cols = " ".join(
            f"{c.name} {c.data_type} {c.description} {' '.join(c.examples)}" for c in self.columns
        )
        return " ".join((self.qualified_name, self.object_type, self.description,
                         self.logic_summary, self.grain, " ".join(self.tags), cols))


@dataclass(frozen=True)
class Relationship:
    left_object: str
    left_column: str
    right_object: str
    right_column: str
    confidence: float = 1.0
    evidence: str = "catalog"

    def other(self, object_name: str) -> tuple[str, str, str] | None:
        if object_name == self.left_object:
            return self.right_object, self.left_column, self.right_column
        if object_name == self.right_object:
            return self.left_object, self.right_column, self.left_column
        return None


@dataclass(frozen=True)
class LineageEdge:
    upstream: str
    downstream: str
    summary: str = ""


@dataclass
class Catalog:
    objects: list[SchemaObject] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    lineage: list[LineageEdge] = field(default_factory=list)
    historical_joins: list[Relationship] = field(default_factory=list)

    def get(self, name: str) -> SchemaObject | None:
        key = name.casefold()
        return next((o for o in self.objects if o.name.casefold() == key or o.qualified_name.casefold() == key), None)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Catalog":
        objects = []
        for raw in payload.get("objects", []):
            columns = tuple(Column(c["name"], c.get("data_type", "unknown"), c.get("nullable", True),
                                  c.get("description", ""), tuple(c.get("examples", ())))
                            for c in raw.get("columns", []))
            objects.append(SchemaObject(raw["name"], columns, raw.get("description", ""),
                                        raw.get("schema", "default"), raw.get("object_type", "table"),
                                        raw.get("logic_summary", ""), raw.get("grain", ""),
                                        tuple(raw.get("tags", ())), raw.get("metadata", {})))
        def rel(r: dict[str, Any]) -> Relationship:
            return Relationship(r["left_object"], r["left_column"], r["right_object"], r["right_column"],
                                float(r.get("confidence", 1.0)), r.get("evidence", "catalog"))
        return cls(objects, [rel(r) for r in payload.get("relationships", [])],
                   [LineageEdge(x["upstream"], x["downstream"], x.get("summary", "")) for x in payload.get("lineage", [])],
                   [rel(r) for r in payload.get("historical_joins", [])])
