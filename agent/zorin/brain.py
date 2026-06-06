from __future__ import annotations

from typing import Any, Dict, Optional


def handle_chat(query: str, session_id: str, conversation_history: Optional[list] = None) -> Dict[str, Any]:
    from agent.graph.graph import run_agent

    return run_agent(query=query, session_id=session_id, conversation_history=conversation_history or [])
