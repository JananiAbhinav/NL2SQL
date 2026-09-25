from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import Catalog, SchemaObject
from .retrieval import HybridRetriever


class SQLSafetyError(ValueError):
    pass


_FORBIDDEN = re.compile(r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|call|execute|copy|unload)\b", re.I)


def validate_read_only_sql(sql: str) -> str:
    """Allow one SELECT/WITH query; reject writes, comments, and extra statements."""
    text = sql.strip()
    if not text:
        raise SQLSafetyError("SQL is empty")
    if "--" in text or "/*" in text or "*/" in text:
        raise SQLSafetyError("SQL comments are not accepted")
    normalized = text.rstrip().rstrip(";").strip()
    if ";" in normalized:
        raise SQLSafetyError("Multiple SQL statements are not allowed")
    if not re.match(r"^(select|with)\b", normalized, re.I):
        raise SQLSafetyError("Only SELECT or WITH queries are allowed")
    if _FORBIDDEN.search(normalized):
        raise SQLSafetyError("Write or DDL operation detected")
    return normalized


class SQLGenerator(Protocol):
    def generate(self, question: str, context: str, dialect: str, previous_sql: str = "",
                 error: str = "") -> str: ...


class SQLExecutor(Protocol):
    def execute(self, sql: str) -> object: ...


@dataclass
class SQLAnswer:
    sql: str
    result: object | None
    tables: list[str]
    attempts: int
    error: str | None = None


class SQLAgent:
    def __init__(self, catalog: Catalog, retriever: HybridRetriever, generator: SQLGenerator,
                 executor: SQLExecutor | None = None, dialect: str = "ansi", max_retries: int = 3,
                 authorization_markers: tuple[str, ...] = ("permission denied", "not authorized", "access denied", "insufficient privilege")):
        self.catalog, self.retriever, self.generator, self.executor = catalog, retriever, generator, executor
        self.dialect = dialect
        self.max_retries = min(max(max_retries, 0), 3)
        self.authorization_markers = tuple(x.casefold() for x in authorization_markers)

    @staticmethod
    def _context(objects: list[SchemaObject], joins: list, question: str) -> str:
        lines = [f"Question: {question}", "Use only these schema objects and columns:"]
        for obj in objects:
            cols = ", ".join(f"{c.name} ({c.data_type})" for c in obj.columns)
            lines.append(f"- {obj.qualified_name}: {obj.description}; grain={obj.grain}; columns=[{cols}]")
            if obj.logic_summary:
                lines.append(f"  logic: {obj.logic_summary}")
        if joins:
            lines.append("Supported join paths:")
            lines.extend(f"- {j.left_object}.{j.left_column} = {j.right_object}.{j.right_column} [{j.evidence}]" for j in joins)
        return "\n".join(lines)

    def answer(self, question: str, top_k: int = 6, previous_sql: str = "") -> SQLAnswer:
        hits = self.retriever.retrieve(question, top_k=top_k)
        objects = [h.object for h in hits]
        names = [o.name for o in objects]
        joins = self.retriever.join_paths(names)
        context = self._context(objects, joins, question)
        sql = ""
        for attempt in range(self.max_retries + 1):
            sql = validate_read_only_sql(self.generator.generate(question, context, self.dialect, previous_sql,
                                                                  "" if attempt == 0 else error))
            if self.executor is None:
                return SQLAnswer(sql, None, names, attempt + 1)
            try:
                return SQLAnswer(sql, self.executor.execute(sql), names, attempt + 1)
            except Exception as exc:  # executor boundary; repair using its concise failure message
                error = str(exc)
                if any(marker in error.casefold() for marker in self.authorization_markers):
                    return SQLAnswer(sql, None, names, attempt + 1, error)
                if attempt >= self.max_retries:
                    return SQLAnswer(sql, None, names, attempt + 1, error)
        raise RuntimeError("unreachable")
