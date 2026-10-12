# leoai/rag_context_manager.py
import asyncio
import json
import logging
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from leoai.db_utils import get_pg_conn, get_async_pg_conn, to_pgvector
from leoai.rag_db_manager import ChatDBManager

logger = logging.getLogger("ContextManager")
DELTA_TO_REFRESH_CONTEXT = timedelta(seconds=10)
PLACE_STATE_KEYS = (
    "selected_place",
    "place_choices",
    "selected_place_knowledge",
)
LOCATION_CONTEXT_KEYS = (*PLACE_STATE_KEYS, "nearby_places", "latitude", "longitude")

SUMMARY_PROMPT_TEMPLATE = """
You are a data extractor. Please analyze the conversation below. Extract key information and return a single, valid JSON object
enclosed in ```json ... ``` markdown block. Do not add any text before or after the JSON block.

Your JSON object MUST have this exact structure:
{{
  "user_profile": {{
    "first_name": "string or null",
    "last_name": "string or null",
    "primary_language": "string or null",
    "primary_email": "string or null",
    "primary_phone": "string or null",
    "personal_interests": ["list of strings"],
    "personality_traits": ["list of strings"],
    "data_labels": ["list of strings"],
    "in_segments": ["list of strings"],
    "in_journey_maps": ["list of strings"],
    "product_interests": ["list of strings"],
    "content_interests": ["list of strings"]
  }},
  "user_context": {{
    "location": "string or null",
    "datetime": "{now_str}"
  }},
  "context_summary": "the summary of long conversation",
  "context_keywords": ["list of keywords from long conversation"],
  "intent_label": "the label of intent from long conversation",
  "intent_confidence": "a probability score between 0 and 1"
}}

--- Conversation ---
{context}
"""


class ContextManager:
    def __init__(self, embedding_model, gemini_client, db_manager: ChatDBManager):
        self.embedding_model = embedding_model
        self.client = gemini_client
        self.db = db_manager

    async def build_context_summary(
        self, user_id, touchpoint_id, cdp_profile_id, user_message, *,
        include_location: bool = True, tenant_id: str = "default",
    ):
        current_context = await asyncio.to_thread(
            self.get_context_summary, user_id, touchpoint_id, tenant_id
        )
        previous_user_context = dict((current_context or {}).get("user_context") or {})
        if not include_location:
            for key in LOCATION_CONTEXT_KEYS:
                previous_user_context.pop(key, None)
        place_state = {
            key: deepcopy(previous_user_context[key])
            for key in PLACE_STATE_KEYS if key in previous_user_context
        }
        touchpoint_context = (
            await self.db.get_touchpoint_context(
                touchpoint_id, user_id=user_id, tenant_id=tenant_id
            )
            if include_location else None
        )
        needs_refresh = self._needs_refresh(current_context)
        if needs_refresh:
            text_context = await self._retrieve_semantic_context(
                user_id, user_message, touchpoint_id, tenant_id=tenant_id
            )
            refreshed = await self._summarize_context(
                user_id, touchpoint_id, cdp_profile_id, text_context
            )
            if refreshed is not None:
                refreshed_user_context = dict(refreshed.get("user_context") or {})
                for key in (PLACE_STATE_KEYS if include_location else LOCATION_CONTEXT_KEYS):
                    refreshed_user_context.pop(key, None)
                previous_user_context.update(refreshed_user_context)
                current_context = {**(current_context or {}), **refreshed}
        current_context = dict(current_context or {})
        previous_user_context.update(place_state)
        if touchpoint_context:
            previous_user_context.update(touchpoint_context)
        current_context["user_context"] = previous_user_context
        if needs_refresh or touchpoint_context or not include_location:
            persisted_context = dict(current_context)
            persisted_context.pop("updated_at", None)
            saved = await self.db.save_context_summary(
                user_id,
                touchpoint_id,
                cdp_profile_id,
                persisted_context,
                tenant_id=tenant_id,
            )
            if not saved:
                raise RuntimeError("Failed to persist conversation context.")
            current_context["updated_at"] = datetime.now(timezone.utc)
        return current_context

    def _needs_refresh(self, context):
        if not context:
            return True
        updated = context.get("updated_at")
        if not updated:
            return True
        now = datetime.now(timezone.utc)
        return (now - updated) > DELTA_TO_REFRESH_CONTEXT

    async def _summarize_context(self, user_id, touchpoint_id, cdp_profile_id, context):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not context:
            return {"user_profile": {}, "user_context": {"datetime": now_str}, "context_keywords": []}
        prompt = SUMMARY_PROMPT_TEMPLATE.format(context=context, now_str=now_str)
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, lambda: self.client.generate_content(prompt))
        match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if not match:
            logger.warning("No valid JSON block in summary output")
            return None
        try:
            summary = json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.exception("Failed to decode conversation summary; preserving saved context")
            return None
        if not isinstance(summary, dict) or not isinstance(summary.get("user_context"), dict):
            logger.warning("Invalid summary structure; preserving saved context")
            return None
        return summary

    async def _retrieve_semantic_context(
        self, user_id, user_message, touchpoint_id, limit=50, *, tenant_id="default"
    ):
        """Include recent turns and semantic matches from this conversation only."""
        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(
            None, lambda: self.embedding_model.encode(
                f"user: {user_message}", normalize_embeddings=True
            ).tolist()
        )
        vector_str = to_pgvector(vector)  # ✅ convert to pgvector format

        async with get_async_pg_conn() as conn:
            recent = await conn.fetch("""
                SELECT message_hash, role, message, created_at FROM chat_messages
                WHERE tenant_id = $1 AND user_id = $2 AND touchpoint_id = $3
                ORDER BY created_at DESC
                LIMIT $4;
            """, tenant_id, user_id, touchpoint_id, min(10, limit))
            matches = await conn.fetch("""
                SELECT cm.message_hash, cm.role, cm.message, cm.created_at
                FROM chat_messages AS cm
                JOIN chat_message_embeddings AS ce
                  ON cm.tenant_id = ce.tenant_id
                 AND cm.message_hash = ce.message_hash
                WHERE cm.tenant_id = $1 AND cm.user_id = $2
                  AND cm.touchpoint_id = $3
                ORDER BY ce.embedding <#> ($4)::vector ASC
                LIMIT $5;
            """, tenant_id, user_id, touchpoint_id, vector_str, limit)

        rows = {row["message_hash"]: row for row in [*matches, *recent]}
        ordered = sorted(rows.values(), key=lambda row: row["created_at"])
        return "\n".join(f"{row['role']}: {row['message']}" for row in ordered)

    def get_context_summary(self, user_id, touchpoint_id, tenant_id="default"):
        """Load the last saved context from DB."""
        with get_pg_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT context_data, updated_at FROM conversational_context
                WHERE tenant_id=%s AND user_id=%s AND touchpoint_id=%s;
            """, (tenant_id, user_id, touchpoint_id))
            row = cur.fetchone()
            if not row:
                return None
            context_data, updated_at = row
            if isinstance(context_data, str):
                context_data = json.loads(context_data)
            context_data["updated_at"] = updated_at
            return context_data
