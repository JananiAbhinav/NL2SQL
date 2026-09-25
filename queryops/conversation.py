from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ConversationState:
    conversation_id: str
    previous_question: str = ""
    previous_sql: str = ""
    matched_tables: list[str] = field(default_factory=list)
    grain: str = ""
    turns: list[dict[str, Any]] = field(default_factory=list)


class ConversationStore:
    """In-memory adapter; replace with a persistent store for multi-process deployments."""
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._states: dict[str, ConversationState] = {}

    def get(self, conversation_id: str) -> ConversationState:
        return self._states.setdefault(conversation_id, ConversationState(conversation_id))

    def record(self, conversation_id: str, question: str, answer: str, sql: str,
               matched_tables: list[str], grain: str = "") -> ConversationState:
        state = self.get(conversation_id)
        state.previous_question, state.previous_sql = question, sql
        state.matched_tables, state.grain = list(matched_tables), grain
        state.turns.append({"question": question, "answer": answer, "sql": sql,
                            "at": datetime.now(timezone.utc).isoformat()})
        state.turns = state.turns[-self.max_turns:]
        return state

    def context_for_followup(self, conversation_id: str) -> dict[str, Any]:
        state = self.get(conversation_id)
        return {"previous_question": state.previous_question, "previous_sql": state.previous_sql,
                "matched_tables": list(state.matched_tables), "grain": state.grain,
                "recent_turns": list(state.turns[-5:])}
