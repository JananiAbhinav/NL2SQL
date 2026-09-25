# QueryOps: hybrid RAG for NL2SQL

This project implements the  blended schema retrieval (BM25-style lexical, dense vector, MMR and attention-style reranking), relationship/lineage expansion, guarded SQL generation and repair, testcase planning, cross-environment comparison helpers, incident RCA context assembly, and structured conversation memory.

Organization-specific sources and integrations are intentionally excluded. Database, embedding, and LLM access are dependency-injected so the package can be connected to a chosen environment without embedding credentials.

# Abstract

Enterprise NL2SQL systems often fail not because large language models cannot produce SQL syntax, but because they are unable to retrieve the correct schema evidence before generation begins. This challenge becomes more severe in enterprise environments where schema ambigu- ity is high, business concepts are duplicated across domains and foreign-key relationships are missing, incomplete or not explicitly maintained.
This project presents QueryOps as a hybrid retrieval-augmented generation platform for NL2SQL that also supports testcase generation, lineage-aware reasoning, cross-environment data comparison and incident root-cause analysis. The RAG implementation combines BM25 lexical retrieval, dense vector search, maximal marginal relevance diversification, attention- based reranking, relationship-aware context expansion, guarded SQL generation and repair loops for failed execution.
This file explains how these components work together to overcome two major barriers in enterprise NL2SQL: schema ambiguity and missing join relationships. Schema ambiguity is ad- dressed through blended retrieval, reranking and transformation-logic summaries derived from DevOps-managed SQL assets, while missing foreign-key relationships are addressed through relationship-aware context construction that supplies executable join paths before SQL genera- tion. The same grounded architecture also injects lineage context to support operational tasks beyond business query answering.
The evaluation strategy covers retrieval quality, SQL correctness, conversational usefulness, safety behavior and operational robustness. The testing across representative scenarios showed satisfactory behavior in schema grounding, follow-up handling and executable SQL generation. This report therefore positions the work not merely as a chatbot implementation, but as a foundation for a measurable and extensible enterprise AI system.

## High Level Architecture
<img width="1984" height="1058" alt="image" src="https://github.com/user-attachments/assets/875586f8-6ea3-40e1-b7dd-61530bd7c236" />

## NL2SQL Flow
<img width="1196" height="1352" alt="image" src="https://github.com/user-attachments/assets/78a85cf9-e3bb-489f-9333-406e38f773eb" />

## Data Comparison Flow
<img width="1196" height="1352" alt="image" src="https://github.com/user-attachments/assets/be26a2f9-1b25-4b37-a8cb-740b677fa12d" />

## Incident RCA Agent
<img width="1196" height="1352" alt="image" src="https://github.com/user-attachments/assets/7f412214-4ab6-401a-adb3-3edd92b48244" />

## Performance Metrics
<img width="1196" height="686" alt="image" src="https://github.com/user-attachments/assets/d078c48a-43f0-46ab-8417-6a256f302c92" />


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
