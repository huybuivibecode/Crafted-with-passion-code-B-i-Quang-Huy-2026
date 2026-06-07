from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.models import Conversation, Message


class MemoryManager:
    def get_or_create_conversation(self, session_id: str) -> Conversation:
        conversation, _ = Conversation.objects.get_or_create(session_id=session_id)
        return conversation

    def get_history(self, session_id: str, limit: int = 20) -> List[dict]:
        conversation = Conversation.objects.filter(session_id=session_id).first()
        if not conversation:
            return []
        latest = list(conversation.messages.order_by("-created_at")[:limit])
        latest.reverse()
        return [
            {
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "metadata": m.metadata or {},
            }
            for m in latest
        ]

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        conversation = self.get_or_create_conversation(session_id)
        return Message.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            intent=intent,
            metadata=metadata or {},
        )
