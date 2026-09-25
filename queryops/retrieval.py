from __future__ import annotations

import math
import re
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import Catalog, Relationship, SchemaObject

TOKEN = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN.findall(text)]


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Small deterministic fallback; replace with a semantic embedding provider in production."""
    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            signed = hashlib.blake2b((token + "!").encode(), digest_size=1).digest()[0] & 1
            index = int.from_bytes(digest, "big") % self.dimensions
            vector[index] += 1.0 if signed else -1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


@dataclass(frozen=True)
class RetrievalHit:
    object: SchemaObject
    score: float
    lexical_score: float = 0.0
    dense_score: float = 0.0


class HybridRetriever:
    def __init__(self, catalog: Catalog, embedder: Embedder | None = None,
                 reranker: Callable[[str, SchemaObject], float] | None = None,
                 lexical_weight: float = 0.5, dense_weight: float = 0.5):
        self.catalog = catalog
        self.embedder = embedder or HashingEmbedder()
        self.reranker = reranker
        self.lexical_weight, self.dense_weight = lexical_weight, dense_weight
        self._texts = [o.searchable_text() for o in catalog.objects]
        self._tokens = [Counter(tokenize(t)) for t in self._texts]
        self._vectors = [self.embedder.embed(t) for t in self._texts]

    def decompose(self, question: str) -> list[str]:
        """Produce lightweight retrieval intents without an LLM dependency."""
        intents = [question.strip()]
        lower = question.casefold()
        cues = [(" by ", "grouping dimensions"), (" per ", "grouping dimensions"),
                (" compare ", "comparison entities"), (" between ", "comparison entities"),
                (" last ", "time filters"), (" during ", "time filters")]
        for cue, label in cues:
            if cue in f" {lower} ":
                intents.append(f"{label} {question}")
        return list(dict.fromkeys(intents))

    def _bm25(self, query: str, index: int) -> float:
        qterms = set(tokenize(query))
        if not qterms:
            return 0.0
        n = len(self._tokens)
        avgdl = sum(sum(c.values()) for c in self._tokens) / max(n, 1)
        doc = self._tokens[index]
        dl = sum(doc.values())
        score = 0.0
        for term in qterms:
            df = sum(term in d for d in self._tokens)
            if term not in doc:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = doc[term]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * dl / max(avgdl, 1)))
        return score

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def _mmr(self, query_vector: list[float], hits: list[RetrievalHit], limit: int,
             diversity: float) -> list[RetrievalHit]:
        chosen: list[RetrievalHit] = []
        remaining = hits[:]
        while remaining and len(chosen) < limit:
            def value(hit: RetrievalHit) -> float:
                idx = self.catalog.objects.index(hit.object)
                redundancy = max((self._cosine(self._vectors[idx], self._vectors[self.catalog.objects.index(x.object)])
                                  for x in chosen), default=0.0)
                return (1 - diversity) * hit.score - diversity * redundancy
            best = max(remaining, key=value)
            chosen.append(best)
            remaining.remove(best)
        return chosen

    def retrieve(self, question: str, top_k: int = 8, candidate_k: int = 24,
                 diversity: float = 0.25, expand_relationships: bool = True,
                 lineage_depth: int = 1) -> list[RetrievalHit]:
        if not self.catalog.objects:
            return []
        intents = self.decompose(question)
        lex = [max((self._bm25(q, i) for q in intents), default=0.0) for i in range(len(self.catalog.objects))]
        dense = [max((self._cosine(self.embedder.embed(q), self._vectors[i]) for q in intents), default=0.0)
                 for i in range(len(self.catalog.objects))]
        maxlex = max(lex, default=0.0) or 1.0
        hits = [RetrievalHit(o, self.lexical_weight * lex[i] / maxlex + self.dense_weight * max(0, dense[i]),
                             lex[i], dense[i]) for i, o in enumerate(self.catalog.objects)]
        pool = sorted(hits, key=lambda h: h.score, reverse=True)[:max(candidate_k, top_k)]
        diverse = self._mmr(self.embedder.embed(question), pool, max(top_k * 2, top_k), diversity)
        if self.reranker:
            diverse = [RetrievalHit(h.object, float(self.reranker(question, h.object)), h.lexical_score, h.dense_score)
                       for h in diverse]
        else:
            # Query-token attention over object, description, and column evidence.
            qt = set(tokenize(question))
            diverse = [RetrievalHit(h.object, h.score + 0.25 * len(qt & set(tokenize(h.object.searchable_text()))) /
                                    max(len(qt), 1), h.lexical_score, h.dense_score) for h in diverse]
        diverse.sort(key=lambda h: h.score, reverse=True)
        seeds = diverse[:top_k]
        if expand_relationships:
            return self._expand(seeds, top_k, lineage_depth)
        return seeds

    def _expand(self, seeds: list[RetrievalHit], top_k: int, lineage_depth: int) -> list[RetrievalHit]:
        selected = {h.object.name: h for h in seeds}
        relationships = self.catalog.relationships + self.catalog.historical_joins
        frontier = set(selected)
        for _ in range(max(0, lineage_depth)):
            for edge in self.catalog.lineage:
                if edge.upstream in frontier and self.catalog.get(edge.downstream):
                    selected.setdefault(edge.downstream, RetrievalHit(self.catalog.get(edge.downstream), 0.01))
                if edge.downstream in frontier and self.catalog.get(edge.upstream):
                    selected.setdefault(edge.upstream, RetrievalHit(self.catalog.get(edge.upstream), 0.01))
            frontier = set(selected)
        # Only add relationship neighbors that form an edge between an already selected object and a seed.
        for rel in relationships:
            if rel.left_object in selected and self.catalog.get(rel.right_object):
                selected.setdefault(rel.right_object, RetrievalHit(self.catalog.get(rel.right_object), 0.02 * rel.confidence))
            if rel.right_object in selected and self.catalog.get(rel.left_object):
                selected.setdefault(rel.left_object, RetrievalHit(self.catalog.get(rel.left_object), 0.02 * rel.confidence))
        return sorted(selected.values(), key=lambda h: h.score, reverse=True)

    def join_paths(self, object_names: list[str], max_depth: int = 4) -> list[Relationship]:
        """Return relationship edges in shortest paths connecting requested objects."""
        edges = self.catalog.relationships + self.catalog.historical_joins
        adjacency: dict[str, list[tuple[str, Relationship]]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.left_object].append((edge.right_object, edge))
            adjacency[edge.right_object].append((edge.left_object, edge))
        result: list[Relationship] = []
        connected = {object_names[0]} if object_names else set()
        for target in object_names[1:]:
            queue = [(x, []) for x in connected]
            visited = set(connected)
            path = None
            while queue:
                node, route = queue.pop(0)
                if node == target:
                    path = route
                    break
                if len(route) >= max_depth:
                    continue
                for neighbor, edge in adjacency[node]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, route + [edge]))
            if path is not None:
                result.extend(path)
                connected.add(target)
        return list(dict.fromkeys(result))
