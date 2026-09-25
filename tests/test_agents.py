from queryops.agents import DataComparisonAgent, IncidentRCAAgent, TestcaseAgent


def test_testcase_generation_uses_column_metadata(catalog, retriever):
    cases = TestcaseAgent(catalog, retriever).generate("orders")
    assert any(c.category == "completeness" for c in cases)
    assert any(c.category == "referential" for c in cases)


def test_comparison_bucket_detection():
    agent = DataComparisonAgent()
    left = agent.bucket_hashes([(1, "a"), (2, "b")])
    right = agent.bucket_hashes([(1, "a"), (2, "c")])
    assert agent.mismatched_buckets(left, right)


def test_comparison_requires_shared_columns():
    import pytest
    with pytest.raises(ValueError):
        DataComparisonAgent().difference_sql("a", "b", [])


def test_incident_context_includes_similar_incident(catalog, retriever):
    agent = IncidentRCAAgent(catalog, retriever, [{"title": "order revenue missing", "resolution": "reload source"}])
    result = agent.investigate("order revenue missing")
    assert result["similar_incidents"]
    assert "likely_objects" in result
