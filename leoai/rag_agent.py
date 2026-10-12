import logging
import asyncio
from typing import Any, List, Optional, TypedDict, Union
from langgraph.graph import END, START, StateGraph
from leoai.ai_core import GeminiClient, get_embedding_model
from leoai.rag_db_manager import (
    ChatDBManager, NearbyLocationUnavailable,
)
from leoai.rag_context_manager import ContextManager
from leoai.rag_prompt_builder import AgentOrchestrator
from leoai.rag_knowledge_manager import KnowledgeRetriever
from leoai.rag_agent_utils import (
    format_nearby_places_answer,
    format_place_picker,
    format_place_selection_confirmation,
    classify_nearby_place_intent,
    is_document_chat,
    is_greeting_message,
    is_nearby_place_question,
    geo_places_search_name,
    nearby_place_terms,
    nearby_radius_meters,
    nearby_result_limit,
    MAX_GEO_PLACES_ENRICHMENT,
    selected_place_index,
    trigger_geo_places_enrichment,
)
from main_config import REDIS_CLIENT

logger = logging.getLogger("RAGAgent")
logger.setLevel(logging.INFO)
DOCUMENT_CHAT_TOUCHPOINT_ID = "document_agent"


def _build_geo_places_enrichment_notice(target_language: str, has_places: bool) -> str:
    """Build the localized notice shown after nearby-place enrichment is queued."""
    is_vietnamese = (target_language or "").lower().startswith(("vi", "vietnam"))
    if is_vietnamese:
        if has_places:
            return (
                "Mình chưa có đủ dữ liệu phù hợp trong bán kính bạn yêu cầu. "
                "Mình đã gửi yêu cầu tìm thêm địa điểm cho bạn. "
                "Vui lòng hỏi lại sau khi quá trình tìm kiếm hoàn tất."
            )
        return (
            "Mình chưa có dữ liệu phù hợp trong bán kính bạn yêu cầu. "
            "Mình đã gửi yêu cầu tìm và bổ sung địa điểm cho bạn. "
            "Vui lòng hỏi lại sau khi quá trình tìm kiếm hoàn tất."
        )
    if has_places:
        return (
            "I do not have enough matching place data within your "
            "requested radius yet. I have queued a search for more "
            "places. Please ask again after the search finishes."
        )
    return (
        "I have no matching place data within your requested radius "
        "yet. I have queued a search to find and add places for you. "
        "Please ask again after the search finishes."
    )


class ChatMessageState(TypedDict, total=False):
    user_id: str
    tenant_id: str
    user_message: str
    cdp_profile_id: str | None
    persona_id: str | None
    touchpoint_id: str | None
    target_language: str
    answer_in_format: str
    temperature_score: float
    keywords: list[str] | None
    latitude: float | None
    longitude: float | None
    touchpoint_name: str
    touchpoint_description: str
    touchpoint_type: str
    touchpoint_keywords: list[str] | None
    result_limit: int | None
    is_nearby_search: bool
    radius_meters: float
    search_name: str
    enrichment_run_id: str
    enrichment_run_id_sink: list[str]
    context: str
    terms: list[str]
    matching_places: list[dict]
    summarized_context: dict
    user_context: dict
    nearby_places: list[dict]
    selected_place: dict | None
    prompt_router: Any
    response: str


class RAGAgent:
    """Coordinate document Q&A, geolocation search, context, and response generation."""

    def __init__(self, gemini_client: Optional[Union[GeminiClient, Any]] = None):
        """Initialize the AI client, retrieval services, and conversation managers."""
        self.client = gemini_client or GeminiClient()
        self.embedding_model = get_embedding_model()
        self.db = ChatDBManager(self.embedding_model)
        self.context = ContextManager(self.embedding_model, self.client, self.db)
        self.knowledge = KnowledgeRetriever(self.embedding_model)
        self.agent_orchestrator = AgentOrchestrator()

    async def create_geolocation_touchpoint(
        self,
        user_id: str,
        latitude: float,
        longitude: float,
        touchpoint_id: Optional[str] = None,
        name: str = "Web visitor",
        description: str = "",
        touchpoint_type: str = "web",
        keywords: Optional[List[str]] = None,
        tenant_id: str = "default",
    ) -> dict:
        """Create or update the user's geolocation touchpoint."""
        return await self.db.upsert_geolocation_touchpoint(
            user_id,
            latitude,
            longitude,
            touchpoint_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            touchpoint_type=touchpoint_type,
            keywords=keywords or [],
        )

    async def process_chat_message(
        self,
        user_id: str,
        user_message: str,
        cdp_profile_id: Optional[str] = None,
        persona_id: Optional[str] = 'personal_assistant',
        touchpoint_id: Optional[str] = None,
        target_language: str = "Vietnamese",
        answer_in_format: str = "text",
        temperature_score: float = 0.85,
        keywords: Optional[List[str]] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        touchpoint_name: str = "Web visitor",
        touchpoint_description: str = "",
        touchpoint_type: str = "web",
        touchpoint_keywords: Optional[List[str]] = None,
        result_limit: int | None = None,
        context: str = "chatbot",
        tenant_id: str = "default",
    ) -> str:
        """Process a chat message and return its response text."""
        result = await self.process_chat_message_with_metadata(
            user_id=user_id,
            user_message=user_message,
            cdp_profile_id=cdp_profile_id,
            persona_id=persona_id,
            touchpoint_id=touchpoint_id,
            target_language=target_language,
            answer_in_format=answer_in_format,
            temperature_score=temperature_score,
            keywords=keywords,
            latitude=latitude,
            longitude=longitude,
            touchpoint_name=touchpoint_name,
            touchpoint_description=touchpoint_description,
            touchpoint_type=touchpoint_type,
            touchpoint_keywords=touchpoint_keywords,
            result_limit=result_limit,
            context=context,
            tenant_id=tenant_id,
        )
        return result["response"]

    async def process_chat_message_with_metadata(
        self,
        user_id: str,
        user_message: str,
        cdp_profile_id: Optional[str] = None,
        persona_id: Optional[str] = 'personal_assistant',
        touchpoint_id: Optional[str] = None,
        target_language: str = "Vietnamese",
        answer_in_format: str = "text",
        temperature_score: float = 0.85,
        keywords: Optional[List[str]] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        touchpoint_name: str = "Web visitor",
        touchpoint_description: str = "",
        touchpoint_type: str = "web",
        touchpoint_keywords: Optional[List[str]] = None,
        result_limit: int | None = None,
        context: str = "chatbot",
        tenant_id: str = "default",
    ) -> dict[str, str | None]:
        """Process one chat message through the compiled RAG workflow.

        The workflow routes document chat, nearby-place search, place selection,
        context building, prompt generation, and response persistence. The
        returned run ID is present only when nearby-place enrichment was queued.

        Args:
            user_id: Identifier for the visitor sending the message.
            user_message: Message text to classify and answer.
            cdp_profile_id: Optional profile identifier. Defaults to None.
            persona_id: Persona used to select prompt behavior.
                Defaults to ``personal_assistant``.
            touchpoint_id: Existing conversation touchpoint. Defaults to None.
            target_language: Language for the response. Defaults to ``Vietnamese``.
            answer_in_format: Retained for API compatibility. Defaults to ``text``.
            temperature_score: Generation temperature. Defaults to ``0.85``.
            keywords: Optional message keywords. Defaults to None.
            latitude: Visitor latitude. Defaults to None.
            longitude: Visitor longitude. Defaults to None.
            touchpoint_name: Display name for a new touchpoint.
            touchpoint_description: Description for a new touchpoint.
            touchpoint_type: Channel type for a new touchpoint.
            touchpoint_keywords: Optional touchpoint keywords.
            result_limit: Optional nearby-place result count.
            context: Chat context used for routing. Defaults to ``chatbot``.

        Returns:
            Response text and an optional Dagster enrichment run ID.
        """
        initial_state: ChatMessageState = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "user_message": user_message,
            "cdp_profile_id": cdp_profile_id,
            "persona_id": persona_id,
            "touchpoint_id": touchpoint_id,
            "target_language": target_language,
            "answer_in_format": answer_in_format,
            "temperature_score": temperature_score,
            "keywords": keywords,
            "latitude": latitude,
            "longitude": longitude,
            "touchpoint_name": touchpoint_name,
            "touchpoint_description": touchpoint_description,
            "touchpoint_type": touchpoint_type,
            "touchpoint_keywords": touchpoint_keywords,
            "result_limit": result_limit,
            "context": context,
        }
        enrichment_run_id_sink: list[str] = []
        initial_state["enrichment_run_id_sink"] = enrichment_run_id_sink
        try:
            if is_document_chat(context, persona_id):
                nearby_intent = {
                    "is_nearby_place_question": False,
                    "terms": [],
                    "search_name": "",
                }
            else:
                nearby_intent = await asyncio.to_thread(
                    classify_nearby_place_intent, user_message
                )
            initial_state.update(
                {
                    "is_nearby_search": nearby_intent["is_nearby_place_question"],
                    "terms": nearby_intent["terms"],
                    "search_name": nearby_intent["search_name"],
                }
            )
            if nearby_intent["is_nearby_place_question"]:
                initial_state.update(
                    {
                        "result_limit": nearby_result_limit(
                            user_message, result_limit
                        ),
                        "radius_meters": nearby_radius_meters(user_message),
                    }
                )
            result = await self._get_chat_graph().ainvoke(initial_state)
            return {
                "response": result["response"],
                "enrichment_run_id": result.get("enrichment_run_id"),
            }
        except Exception as e:
            logger.exception("❌ RAG pipeline error")
            return {
                "response": f"I'm sorry, but something went wrong: {e}",
                "enrichment_run_id": (
                    enrichment_run_id_sink[0] if enrichment_run_id_sink else None
                ),
            }

    def _get_chat_graph(self):
        """Build and cache the LangGraph workflow used for standard chat."""
        graph = getattr(self, "_chat_graph", None)
        if graph is not None:
            return graph

        workflow = StateGraph(ChatMessageState)
        workflow.add_node("document_chat", self._chat_document_node)
        workflow.add_node("validate_input", self._validate_input_node)
        workflow.add_node("nearby_places", self._nearby_places_node)
        workflow.add_node("enrich_geo_places", self._enrich_geo_places_node)
        workflow.add_node("save_nearby_exchange", self._save_nearby_exchange_node)
        workflow.add_node("prepare_touchpoint", self._prepare_touchpoint_node)
        workflow.add_node("save_user_message", self._save_user_message_node)
        workflow.add_node("build_context", self._build_context_node)
        workflow.add_node("place_picker", self._place_picker_node)
        workflow.add_node("place_selection", self._place_selection_node)
        workflow.add_node("build_prompt", self._build_prompt_node)
        workflow.add_node("generate_answer", self._generate_answer_node)
        workflow.add_node("save_answer", self._save_answer_node)

        workflow.add_conditional_edges(
            START,
            self._route_chat_type,
            {"document_chat": "document_chat", "standard_chat": "validate_input"},
        )
        workflow.add_edge("document_chat", END)
        workflow.add_conditional_edges(
            "validate_input",
            self._route_after_validation,
            {"nearby_places": "nearby_places", "standard_chat": "prepare_touchpoint"},
        )
        workflow.add_conditional_edges(
            "nearby_places",
            self._route_after_nearby_places,
            {"enrich_geo_places": "enrich_geo_places", "finish": "save_nearby_exchange"},
        )
        workflow.add_edge("enrich_geo_places", "save_nearby_exchange")
        workflow.add_edge("save_nearby_exchange", END)
        workflow.add_edge("prepare_touchpoint", "save_user_message")
        workflow.add_edge("save_user_message", "build_context")
        workflow.add_conditional_edges(
            "build_context",
            self._route_after_context,
            {
                "place_picker": "place_picker",
                "place_selection": "place_selection",
                "generate_answer": "build_prompt",
            },
        )
        workflow.add_edge("place_picker", END)
        workflow.add_edge("place_selection", END)
        workflow.add_edge("build_prompt", "generate_answer")
        workflow.add_edge("generate_answer", "save_answer")
        workflow.add_edge("save_answer", END)

        self._chat_graph = workflow.compile()
        return self._chat_graph

    @staticmethod
    def _route_chat_type(state: ChatMessageState) -> str:
        """Route document-chat requests away from geolocation conversation state."""
        if is_document_chat(state["context"], state.get("persona_id")):
            return "document_chat"
        return "standard_chat"

    def _validate_input_node(self, state: ChatMessageState) -> dict:
        """Validate coordinates and derive nearby-search terms and result limits."""
        if (state.get("latitude") is None) != (state.get("longitude") is None):
            raise ValueError("latitude and longitude must be provided together")
        if not state.get("is_nearby_search", False):
            return {}
        return {}

    @staticmethod
    def _route_after_validation(state: ChatMessageState) -> str:
        """Choose nearby-place search or the normal touchpoint workflow."""
        if state.get("is_nearby_search", False):
            return "nearby_places"
        return "standard_chat"

    async def _chat_document_node(self, state: ChatMessageState) -> dict:
        """Run document Q&A and return its response to the workflow."""
        response = await self._process_document_chat(
            state["user_id"],
            state["user_message"],
            state.get("cdp_profile_id"),
            state.get("persona_id"),
            state["target_language"],
            state["answer_in_format"],
            state["temperature_score"],
            state["tenant_id"],
        )
        return {"response": response}

    async def _nearby_places_node(self, state: ChatMessageState) -> dict:
        """Search local places within the requested radius before any AI or enrichment."""
        result_limit = state.get("result_limit")
        if result_limit is None:
            raise RuntimeError("Nearby search requires a validated result limit.")
        try:
            places = await self.db.find_nearby_places(
                state.get("touchpoint_id"),
                state["terms"],
                result_limit,
                user_id=state["user_id"],
                latitude=state.get("latitude"),
                longitude=state.get("longitude"),
                radius_meters=state["radius_meters"],
                tenant_id=state["tenant_id"],
            )
        except NearbyLocationUnavailable:
            logger.info(
                "Nearby search requires location for visitor %s",
                state["user_id"],
            )
            response = (
                "Hãy chia sẻ vị trí của bạn để mình tìm các địa điểm gần nhất."
                if (state["target_language"] or "").lower().startswith(("vi", "vietnam"))
                else "Please share your location so I can find nearby places."
            )
            return {"response": response}

        response = format_nearby_places_answer(
            places,
            state["target_language"],
            state["terms"],
            state["answer_in_format"],
        )
        return {"response": response, "matching_places": places}

    @staticmethod
    def _route_after_nearby_places(state: ChatMessageState) -> str:
        """Enrich incomplete searches; missing location is not an empty result."""
        places = state.get("matching_places")
        result_limit = state.get("result_limit")
        if (
            places is not None
            and result_limit is not None
            and len(places) < result_limit
        ):
            return "enrich_geo_places"
        return "finish"

    async def _enrich_geo_places_node(self, state: ChatMessageState) -> dict:
        """Queue bounded place discovery and knowledge enrichment without waiting."""
        result_limit = state.get("result_limit")
        if result_limit is None:
            raise RuntimeError("Nearby enrichment requires a validated result limit.")
        places = state.get("matching_places", [])
        count = min(
            result_limit - len(places),
            MAX_GEO_PLACES_ENRICHMENT,
        )
        if count <= 0:
            raise RuntimeError("Nearby enrichment requires missing place results.")

        latitude, longitude = await self.db.resolve_nearby_location(
            state.get("touchpoint_id"),
            user_id=state["user_id"],
            latitude=state.get("latitude"),
            longitude=state.get("longitude"),
            tenant_id=state["tenant_id"],
        )
        run_id = await asyncio.to_thread(
            trigger_geo_places_enrichment,
            name=state["search_name"],
            latitude=latitude,
            longitude=longitude,
            radius=state["radius_meters"],
            count=count,
        )
        run_id_sink = state.get("enrichment_run_id_sink")
        if run_id_sink is not None:
            run_id_sink.append(run_id)
        notice = _build_geo_places_enrichment_notice(
            state["target_language"], has_places=bool(places)
        )
        if places:
            response = format_nearby_places_answer(
                places,
                state["target_language"],
                state["terms"],
                state["answer_in_format"],
            )
            notice = f"<p>{notice}</p>" if state["answer_in_format"] == "html" else notice
            separator = "" if state["answer_in_format"] == "html" else "\n\n"
            response = f"{response}{separator}{notice}"
        else:
            response = notice
        return {"response": response, "enrichment_run_id": run_id}

    async def _save_nearby_exchange_node(self, state: ChatMessageState) -> dict:
        """Save a nearby answer after search or successful enrichment submission."""
        if "matching_places" not in state:
            return {}
        for role, message in (("user", state["user_message"]), ("bot", state["response"])):
            await self.db.save_chat_message(
                state["user_id"],
                role,
                message,
                state.get("cdp_profile_id"),
                state.get("persona_id"),
                state.get("touchpoint_id") or "web_leobot",
                tenant_id=state["tenant_id"],
                embed=False,
            )
        return {}

    async def _prepare_touchpoint_node(self, state: ChatMessageState) -> dict:
        """Create a coordinate-backed touchpoint or select the web fallback."""
        touchpoint_id = state.get("touchpoint_id")
        if state.get("latitude") is not None and state.get("longitude") is not None:
            touchpoint = await self.create_geolocation_touchpoint(
                state["user_id"],
                state["latitude"],
                state["longitude"],
                touchpoint_id,
                tenant_id=state["tenant_id"],
                name=state["touchpoint_name"],
                description=state["touchpoint_description"],
                touchpoint_type=state["touchpoint_type"],
                keywords=state.get("touchpoint_keywords") or [],
            )
            touchpoint_id = touchpoint["touchpoint_id"]
        return {"touchpoint_id": touchpoint_id or "web_leobot"}

    async def _save_user_message_node(self, state: ChatMessageState) -> dict:
        """Persist the user message without stopping the chat on logging failure."""
        try:
            logger.info("🧠 insert user message: %s", state["user_message"])
            await self.db.save_chat_message(
                user_id=state["user_id"],
                role="user",
                message=state["user_message"],
                cdp_profile_id=state.get("cdp_profile_id"),
                persona_id=state.get("persona_id"),
                touchpoint_id=state["touchpoint_id"],
                keywords=state.get("keywords"),
                tenant_id=state["tenant_id"],
            )
        except Exception as exc:
            logger.error("❌ Failed to save user message to DB: %s", exc)
        return {}

    async def _build_context_node(self, state: ChatMessageState) -> dict:
        """Load summarized conversation context and its place-selection state."""
        summarized_context = await self.context.build_context_summary(
            state["user_id"],
            state["touchpoint_id"],
            state.get("cdp_profile_id"),
            state["user_message"],
            tenant_id=state["tenant_id"],
        )
        user_context = summarized_context.get("user_context", {})
        return {
            "summarized_context": summarized_context,
            "user_context": user_context,
            "nearby_places": user_context.get("nearby_places", [])[:10],
            "selected_place": user_context.get("selected_place"),
        }

    def _route_after_context(self, state: ChatMessageState) -> str:
        """Route greetings, place selections, and ordinary questions."""
        nearby_places = state.get("nearby_places", [])
        if (
            is_greeting_message(state["user_message"])
            and nearby_places
            and not state.get("selected_place")
        ):
            return "place_picker"
        place_choices = state["user_context"].get("place_choices", nearby_places)
        if selected_place_index(state["user_message"], len(place_choices)) is not None:
            return "place_selection"
        return "generate_answer"

    async def _place_picker_node(self, state: ChatMessageState) -> dict:
        """Persist available places and ask the visitor to choose one."""
        user_context = dict(state["user_context"])
        user_context["place_choices"] = [
            dict(place) for place in state["nearby_places"]
        ]
        summary = dict(state["summarized_context"])
        summary["user_context"] = user_context
        persisted_context = dict(summary)
        persisted_context.pop("updated_at", None)
        if not await self.db.save_context_summary(
            state["user_id"],
            state["touchpoint_id"],
            state.get("cdp_profile_id"),
            persisted_context,
            tenant_id=state["tenant_id"],
        ):
            raise RuntimeError("Failed to save the nearby-place choices.")
        response = format_place_picker(
            state["nearby_places"], state["target_language"]
        )
        await self.db.save_chat_message(
            state["user_id"],
            "bot",
            response,
            state.get("cdp_profile_id"),
            state.get("persona_id"),
            state["touchpoint_id"],
            tenant_id=state["tenant_id"],
        )
        return {"response": response}

    async def _place_selection_node(self, state: ChatMessageState) -> dict:
        """Persist the visitor's selected place and confirm the selection."""
        nearby_places = state.get("nearby_places", [])
        user_context = dict(state["user_context"])
        place_choices = user_context.get("place_choices", nearby_places)
        selection_index = selected_place_index(
            state["user_message"], len(place_choices)
        )
        if selection_index is None:
            raise RuntimeError("Place selection route lost its selected place.")
        selected_place = dict(place_choices[selection_index])
        user_context["selected_place"] = selected_place

        summary = dict(state["summarized_context"])
        summary["user_context"] = user_context
        persisted_context = dict(summary)
        persisted_context.pop("updated_at", None)
        if not await self.db.save_context_summary(
            state["user_id"],
            state["touchpoint_id"],
            state.get("cdp_profile_id"),
            persisted_context,
            tenant_id=state["tenant_id"],
        ):
            raise RuntimeError("Failed to save the selected place.")
        response = format_place_selection_confirmation(
            selected_place, state["target_language"]
        )
        await self.db.save_chat_message(
            state["user_id"],
            "bot",
            response,
            state.get("cdp_profile_id"),
            state.get("persona_id"),
            state["touchpoint_id"],
            tenant_id=state["tenant_id"],
        )
        return {"response": response, "selected_place": selected_place}

    async def _build_prompt_node(self, state: ChatMessageState) -> dict:
        """Enrich context with place knowledge and build the response prompt."""
        summarized_context = dict(state["summarized_context"])
        user_context = dict(summarized_context.get("user_context") or {})
        selected_place = user_context.get("selected_place")
        if selected_place:
            place_knowledge = await self._retrieve_selected_place_knowledge(
                selected_place, state["user_message"], state["tenant_id"]
            )
            if place_knowledge:
                user_context["selected_place_knowledge"] = place_knowledge
                summarized_context["user_context"] = user_context

        first_name = (summarized_context.get("user_profile") or {}).get("first_name")
        if first_name:
            REDIS_CLIENT.hset(
                state["user_id"], mapping={"profile_id": "", "name": first_name}
            )
        prompt_router = self.agent_orchestrator.build_prompt(
            state["user_message"],
            summarized_context,
            state["target_language"],
            state.get("persona_id"),
        )
        logger.info("🧠 Detected purpose: %s", prompt_router.purpose)
        logger.info("📝 Prompt snippet: %s...", prompt_router.prompt_text[:200])
        return {
            "summarized_context": summarized_context,
            "user_context": user_context,
            "prompt_router": prompt_router,
        }

    async def _generate_answer_node(self, state: ChatMessageState) -> dict:
        """Generate a response using the routed prompt and temperature."""
        response = await self._safe_generate(
            state["prompt_router"], state["temperature_score"]
        )
        return {"response": response}

    async def _save_answer_node(self, state: ChatMessageState) -> dict:
        """Persist generated text responses; skip persistence for report prompts."""
        if state["prompt_router"].purpose == "generate_text":
            logger.info("🧠 insert bot message: %s", state["response"])
            await self.db.save_chat_message(
                state["user_id"],
                "bot",
                state["response"],
                state.get("cdp_profile_id"),
                state.get("persona_id"),
                state["touchpoint_id"],
                tenant_id=state["tenant_id"],
            )
        return {}

    async def _retrieve_selected_place_knowledge(
        self, selected_place: dict, user_message: str, tenant_id: str = "default"
    ) -> str:
        """Retrieve focused knowledge for the selected place when supported."""
        retriever = getattr(self, "knowledge", None)
        retrieve = getattr(retriever, "retrieve_selected_place", None)
        if retrieve is None:
            return ""
        return await retrieve(
            selected_place, user_message, tenant_id=tenant_id, limit=3
        )

    async def _process_document_chat(
        self,
        user_id: str,
        user_message: str,
        cdp_profile_id: str | None,
        persona_id: str | None,
        target_language: str,
        answer_in_format: str,
        temperature_score: float,
        tenant_id: str,
    ) -> str:
        """Answer document questions on an isolated document-chat touchpoint."""
        await self.db.save_chat_message(
            user_id, "user", user_message, cdp_profile_id, persona_id,
            DOCUMENT_CHAT_TOUCHPOINT_ID, tenant_id=tenant_id,
        )
        summary = await self.context.build_context_summary(
            user_id, DOCUMENT_CHAT_TOUCHPOINT_ID, cdp_profile_id, user_message,
            include_location=False, tenant_id=tenant_id,
        )
        document_context = ""
        if not is_greeting_message(user_message):
            document_context = await self.knowledge.retrieve(
                user_message, tenant_id, user_id=user_id,
            )
        prompt = self.agent_orchestrator.build_document_prompt(
            user_message, summary, document_context, target_language,
        )
        answer = await self._safe_generate(prompt, temperature_score)
        await self.db.save_chat_message(
            user_id, "bot", answer, cdp_profile_id, persona_id,
            DOCUMENT_CHAT_TOUCHPOINT_ID, tenant_id=tenant_id,
        )
        return answer

    async def _safe_generate(self, prompt_router, temperature_score: float) -> str:
        """Run either synchronous or asynchronous client generation safely."""
        # Select the generation method required by the prompt purpose.
        if prompt_router.purpose == "generate_report":
            method = self.client.generate_report
        else:
            method = self.client.generate_content

        generation_kwargs: dict[str, Any] = {"temperature": temperature_score}
        if prompt_router.purpose != "generate_report" and isinstance(self.client, GeminiClient):
            generation_kwargs["system_instruction"] = prompt_router.system_instruction

        # Handle async and sync clients without blocking the event loop.
        if asyncio.iscoroutinefunction(method):
            return await method(prompt_router.prompt_text, **generation_kwargs)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, lambda: method(prompt_router.prompt_text, **generation_kwargs)
            )
