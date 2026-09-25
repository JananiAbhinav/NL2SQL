from queryops.conversation import ConversationStore


def test_conversation_keeps_structured_followup_context():
    store = ConversationStore(max_turns=2)
    store.record("c1", "revenue by region", "ok", "SELECT 1", ["orders"], "region")
    context = store.context_for_followup("c1")
    assert context["previous_sql"] == "SELECT 1"
    assert context["matched_tables"] == ["orders"]
    assert context["grain"] == "region"
