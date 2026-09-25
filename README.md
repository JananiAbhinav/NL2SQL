# QueryOps: hybrid RAG for NL2SQL

This project implements the  blended schema retrieval (BM25-style lexical, dense vector, MMR and attention-style reranking), relationship/lineage expansion, guarded SQL generation and repair, testcase planning, cross-environment comparison helpers, incident RCA context assembly, and structured conversation memory.

Organization-specific sources and integrations are intentionally excluded. Database, embedding, and LLM access are dependency-injected so the package can be connected to a chosen environment without embedding credentials.

## Quick start

```bash
python -m queryops demo
python -m queryops retrieve "monthly sales by region" --catalog examples/catalog.json
```

Install optional integrations only when needed:

```bash
pip install -e '.[embeddings,sql,dev]'
```

The default implementation uses a deterministic hashed-token vectorizer for a zero-configuration demo. For production, inject a semantic embedding provider, LLM, SQL executor, and persistent metadata store. See `examples/catalog.json` for the portable catalog format.

## Databricks connection example

Credentials are deliberately not enabled. Configure secrets outside source control before connecting an executor.

```python
# from databricks import sql
# connection = sql.connect(
#     server_hostname="<workspace-host>",
#     http_path="<warehouse-http-path>",
#     access_token="<read-from-secret-manager>",
# )
```

## Safety

Generated SQL is treated as untrusted. The guard permits read-only SELECT/WITH statements and rejects multiple statements and common write/DDL operations. This is a conservative application-level check, not a replacement for database-side read-only credentials, resource limits, or query auditing.

## Components

- `HybridRetriever`: decomposes question intents, blends lexical and dense candidates, applies MMR, reranks, then expands relationship paths and lineage.
- `SQLAgent`: asks an injected generator for SQL grounded in retrieved context and retries execution failures up to three times; authorization errors stop immediately.
- `TestcaseAgent`, `DataComparisonAgent`, and `IncidentRCAAgent`: build structured task plans from the same catalog and context types.
- `ConversationStore`: keeps structured query state and a bounded turn history.

Run the suite with `pytest`.
