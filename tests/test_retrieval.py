from queryops.retrieval import HashingEmbedder


def test_retrieval_finds_relevant_object(retriever):
    hits = retriever.retrieve("total order revenue by date", top_k=1, expand_relationships=False)
    assert hits[0].object.name == "orders"


def test_relationship_expansion_adds_joinable_dimension(retriever):
    hits = retriever.retrieve("order revenue", top_k=1)
    assert {h.object.name for h in hits} >= {"orders", "customers"}


def test_join_path_returns_relationship(retriever):
    path = retriever.join_paths(["orders", "customers"])
    assert len(path) == 1
    assert path[0].left_column == "customer_id"


def test_hash_embedder_produces_unit_norm():
    vector = HashingEmbedder(32).embed("revenue order")
    assert abs(sum(x*x for x in vector) - 1.0) < 1e-9
