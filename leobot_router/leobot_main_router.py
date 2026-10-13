import asyncio
import json
import logging
import time
from html import escape
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import (
    HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse,
)
from dagster_graphql import DagsterGraphQLClientError
from redis.exceptions import RedisError
from leoai.geo_place_events import wait_for_geo_places_ready
from leoai.chat_response_cache import ChatResponseCache
from leoai.ai_intent_detection import IntentDetector, IntentType, RequestContext
from leoai.leo_datamodel import GeolocationTouchpointRequest, Message
from leoai.leo_personalization import _build_recommended_actions
from leoai.rag_agent import (
    DOCUMENT_CHAT_TOUCHPOINT_ID, RAGAgent,
    nearby_result_limit,
)
from leoai.rag_agent_utils import (
    get_geo_places_enrichment_status,
    nearby_radius_meters,
    format_nearby_places_answer,
)
from leoai.ai_core import is_ai_model_ready

from main_config import (
    CDP_TRACKING,
    HOSTNAME,
    LEOBOT_DEV_MODE,
    REDIS_CLIENT,
)
from leobot_router.leobot_request_filter import (
    RequestFilterUnavailable,
    chat_request_filter,
    is_safe_to_answer,
)

# Router and logger initialization
logger = logging.getLogger("leobot-router")
router = APIRouter()
rag_agent = RAGAgent()
intent_detector = IntentDetector()
chat_response_cache = ChatResponseCache()
ENRICHMENT_STATUS_POLL_SECONDS = 2
TERMINAL_DAGSTER_STATUSES = {"SUCCESS", "FAILURE", "CANCELED"}


# === Core UI Routes ===
@router.get("/", response_class=HTMLResponse)
@router.get("/_leoai", response_class=HTMLResponse)
async def index(request: Request):
    """
    Root index page for the chatbot demo.
    Loads from Jinja2 template (index.html).
    """
    ts = int(time.time())
    data = {"request": request, "HOSTNAME": HOSTNAME,
            "LEOBOT_DEV_MODE": LEOBOT_DEV_MODE, "CDP_TRACKING": CDP_TRACKING, "timestamp": ts}
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html", data)


# === Main Chat API ===
@router.post("/_leoai/ask", response_class=JSONResponse)
@router.post("/ask", response_class=JSONResponse)
async def handle_chat(msg: Message):
    """
    Main endpoint for user → AI chat messages.
    Handles rate-limiting, message length validation, and response generation.
    """
    # 1. Validate input and rate-limit before any model calls.
    try:
        filtered_request = chat_request_filter.filter(
            msg.visitor_id,
            msg.question,
            consume_limit=False,
        )
    except HTTPException as exc:
        error_code = 510 if exc.status_code == 413 else exc.status_code
        return {"error": True, "error_code": error_code, "answer": exc.detail}

    # Keep using the normalized visitor ID for state and rate limiting.
    visitor_id = filtered_request.visitor_id
    try:
        if not await asyncio.to_thread(is_safe_to_answer, visitor_id):
            return {"error": True, "error_code": 429, "answer": "Too many messages"}
    except RequestFilterUnavailable:
        logger.exception("Unable to enforce chat rate limit")
        raise HTTPException(status_code=503, detail="Chat service temporarily unavailable")

    profile_id = await asyncio.to_thread(
        REDIS_CLIENT.hget, visitor_id, "profile_id"
    ) or None
    document_context = (
        msg.context == "agent" and msg.persona_id == "personal_assistant"
    )
    active_touchpoint_id = msg.touchpoint_id
    if not active_touchpoint_id and not document_context:
        active_touchpoint_id = await asyncio.to_thread(
            REDIS_CLIENT.hget, visitor_id, "touchpoint_id"
        )
    if isinstance(profile_id, bytes):
        profile_id = profile_id.decode("utf-8")
    if isinstance(active_touchpoint_id, bytes):
        active_touchpoint_id = active_touchpoint_id.decode("utf-8")
    cache_request = None
    try:
        cache_request, cached_response = await chat_response_cache.lookup(
            visitor_id,
            {
                **msg.model_dump(mode="json"),
                "visitor_id": visitor_id,
                "active_touchpoint_id": active_touchpoint_id,
                "profile_id": profile_id,
            },
        )
    except (RedisError, ValueError):
        logger.exception("Chat response cache lookup failed; processing the request.")
    else:
        if cached_response is not None:
            return cached_response

    # 2. Classify once, keeping channel metadata separate from the user's intent.
    intent_result = await intent_detector.detect_async(
        msg.question,
        RequestContext(
            channel="web_widget",
            visitor_id=visitor_id,
            context=msg.context,
            persona_id=msg.persona_id,
        ),
    )
    intent_is_clear = not intent_result.needs_clarification
    document_chat = False
    nearby_search = False

    match intent_result.primary_intent:
        case IntentType.DOCUMENT_CHAT:
            document_chat = intent_is_clear
        case IntentType.LOCATION_CHAT:
            nearby_search = intent_is_clear
        case IntentType.GENERAL_CHAT:
            pass
        case _:
            # TODO: Add dedicated handlers for intents beyond document/location/general.
            if intent_is_clear:
                logger.debug(
                    "No specialized handler for intent '%s'; using general chat",
                    intent_result.primary_intent.value,
                )

    # 3. Validate location parameters only for a clear location/chat request.
    result_limit = msg.result_limit
    radius_meters = None
    if nearby_search:
        try:
            result_limit = nearby_result_limit(
                msg.question,
                msg.result_limit,
                intent_limit=intent_result.entities.get("result_limit"),
            )
            radius_meters = nearby_radius_meters(
                msg.question,
                intent_result.entities.get("radius_meters"),
            )
        except ValueError as exc:
            logger.warning("Invalid nearby-place parameters: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if (
        intent_is_clear
        and not document_chat
        and (msg.latitude is None) != (msg.longitude is None)
    ):
        raise HTTPException(status_code=400, detail="latitude and longitude must be provided together")

    # 5. Select the isolated document touchpoint or the visitor's active one.
    if document_chat:
        touchpoint_id = DOCUMENT_CHAT_TOUCHPOINT_ID
    else:
        touchpoint_id = active_touchpoint_id
        if not touchpoint_id and document_context:
            touchpoint_id = await asyncio.to_thread(
                REDIS_CLIENT.hget, visitor_id, "touchpoint_id"
            )
            if isinstance(touchpoint_id, bytes):
                touchpoint_id = touchpoint_id.decode("utf-8")
            cache_request = None

    if (
        touchpoint_id is None
        and msg.latitude is not None
        and msg.longitude is not None
        and not nearby_search
        and not document_chat
        and intent_is_clear
    ):
        touchpoint = await rag_agent.create_geolocation_touchpoint(
            visitor_id, msg.latitude, msg.longitude
        )
        touchpoint_id = touchpoint["touchpoint_id"]

    # 6. Pass the same result into RAG and format its response.
    chat_result = await rag_agent.process_chat_message_with_metadata(
        user_id=visitor_id,
        user_message=msg.question,
        persona_id=msg.persona_id,
        cdp_profile_id=profile_id,
        touchpoint_id=touchpoint_id,
        target_language=msg.answer_in_language or "English",
        answer_in_format=msg.answer_in_format,
        latitude=None if document_chat else msg.latitude,
        longitude=None if document_chat else msg.longitude,
        touchpoint_name=msg.touchpoint_name,
        touchpoint_description=msg.touchpoint_description,
        touchpoint_type=msg.touchpoint_type,
        touchpoint_keywords=msg.touchpoint_keywords,
        result_limit=result_limit,
        radius_meters=radius_meters,
        context=msg.context,
        temperature_score=msg.temperature_score,
        channel="web_widget",
        intent_result=intent_result,
    )
    response = {
        "question": msg.question,
        "answer": chat_result["response"],
        "visitor_id": visitor_id,
        "touchpoint_id": touchpoint_id,
        "error_code": 500 if chat_result.get("error") else 0,
    }
    if chat_result.get("error"):
        response["error"] = True
    if nearby_search:
        response["places"] = chat_result.get("places", [])
        response["similar_places"] = chat_result.get("similar_places", [])
        if response["similar_places"]:
            response["similar_places_notice"] = (
                "Gợi ý tương tự, không phải kết quả khớp tên bạn tìm."
                if (msg.answer_in_language or "").lower().startswith(("vi", "vietnam"))
                else "Similar suggestions, not name matches for your search."
            )
            notice = response["similar_places_notice"]
            response["similar_places_answer"] = (
                f"<p><strong>{escape(notice)}</strong></p>"
                if msg.answer_in_format == "html"
                else f"{notice}\n\n"
            ) + format_nearby_places_answer(
                response["similar_places"],
                msg.answer_in_language or "English",
                [],
                msg.answer_in_format,
            )
    run_id = chat_result["enrichment_run_id"]
    if run_id:
        response["enrichment_run_id"] = run_id
        response["enrichment_status_url"] = str(
            router.url_path_for("geo_places_enrichment_events", run_id=run_id)
        )
    if cache_request is not None and not response.get("error"):
        try:
            await chat_response_cache.store(cache_request, response)
        except (RedisError, ValueError):
            logger.exception("Chat response cache write failed; returning fresh results.")
    return response


@router.get(
    "/_leoai/geo-places/enrichment/{run_id}/events",
    name="geo_places_enrichment_events",
)
async def geo_places_enrichment_events(run_id: str):
    """Stream committed discovery readiness before slower Dagster enrichment finishes."""

    async def status_events():
        last_status = None
        yield "retry: 5000\n\n"
        ready_task = asyncio.create_task(wait_for_geo_places_ready(run_id))
        status_task = None
        try:
            while True:
                if status_task is None:
                    status_task = asyncio.create_task(
                        asyncio.to_thread(get_geo_places_enrichment_status, run_id)
                    )
                watched_tasks: set[asyncio.Task[object]] = {status_task}
                if ready_task is not None:
                    watched_tasks.add(ready_task)
                await asyncio.wait(watched_tasks, return_when=asyncio.FIRST_COMPLETED)
                if ready_task is not None and ready_task.done():
                    try:
                        event = ready_task.result()
                    except (RedisError, ValueError):
                        logger.exception(
                            "Redis discovery notification unavailable for run %s; "
                            "falling back to Dagster status.",
                            run_id,
                        )
                        ready_task = None
                    else:
                        yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                        return

                try:
                    if not status_task.done():
                        continue
                    status = status_task.result()
                except DagsterGraphQLClientError:
                    logger.exception(
                        "Unable to stream Dagster status for enrichment run %s", run_id
                    )
                    yield "event: status_error\ndata: {}\n\n"
                    return
                status_task = None

                if status != last_status:
                    event = json.dumps(
                        {"run_id": run_id, "status": status},
                        separators=(",", ":"),
                    )
                    yield f"data: {event}\n\n"
                    last_status = status

                if status in TERMINAL_DAGSTER_STATUSES:
                    try:
                        await chat_response_cache.invalidate_places()
                    except RedisError:
                        logger.exception("Failed to invalidate chat cache for run %s", run_id)
                    return

                if ready_task is not None:
                    await asyncio.wait(
                        {ready_task}, timeout=ENRICHMENT_STATUS_POLL_SECONDS
                    )
                else:
                    await asyncio.sleep(ENRICHMENT_STATUS_POLL_SECONDS)
                yield ": keep-alive\n\n"
        finally:
            tasks: list[asyncio.Task[object]] = [
                task for task in (ready_task, status_task) if task is not None
            ]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return StreamingResponse(
        status_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )



# === demo-chatbot-ishop ===
@router.get("/_leoai/demo-chatbot-ishop", response_class=HTMLResponse)
async def demo_chat_in_ishop(request: Request):
    """
    Demo chatbot page for iShop UI.
    """
    ts = int(time.time())
    data = {"request": request, "HOSTNAME": HOSTNAME,
            "LEOBOT_DEV_MODE": LEOBOT_DEV_MODE, "timestamp": ts}
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "demo-chatbot-ishop.html", data)

# === chat-with-docss ===
@router.get("/chat-with-docs", response_class=HTMLResponse)
@router.get("/_leoai/chat-with-docs", response_class=HTMLResponse)
async def chat_with_docs(request: Request):
    """
    Demo chatbot chat-with-docs
    """
    ts = int(time.time())
    data = {"request": request, "HOSTNAME": HOSTNAME,
            "LEOBOT_DEV_MODE": LEOBOT_DEV_MODE, "timestamp": ts}
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "chat-with-docs.html", data)


# === Health Check Routes ===

@router.get("/ping", response_class=PlainTextResponse)
@router.get("/_leoai/ping", response_class=PlainTextResponse)
async def ping():
    """Simple service heartbeat check."""
    return "PONG"


@router.get("/_leoai/is-ready", response_class=JSONResponse)
@router.post("/_leoai/is-ready", response_class=JSONResponse)
async def is_ready():
    """Check whether the configured hosted AI provider has credentials."""
    return {"ok": is_ai_model_ready()}


# === Visitor Info Endpoint ===
@router.get("/_leoai/visitor-info", response_class=JSONResponse)
@router.get("/visitor-info", response_class=JSONResponse)
async def get_visitor_info(
    visitor_id: str = Query(...),
    name: str | None = None,
    touchpoint_id: str | None = None,
):
    """
    Fetch or update visitor info stored in Redis.
    Used to persist visitor names and touchpoints across sessions.
    """
    visitor_id = visitor_id.strip()
    if not visitor_id:
        return JSONResponse(status_code=400, content={"error": "visitor_id is empty"})

    redis_data = REDIS_CLIENT.hgetall(visitor_id)
    cached_name = redis_data.get("name", "")
    cached_touchpoint = redis_data.get("touchpoint_id", "")

    # Update cache only if new values differ
    updates = {}
    if name and name != cached_name:
        updates["name"] = name
    if touchpoint_id and touchpoint_id != cached_touchpoint:
        updates["touchpoint_id"] = touchpoint_id
    if updates:
        REDIS_CLIENT.hset(visitor_id, mapping=updates)
        try:
            await chat_response_cache.invalidate_visitor(visitor_id)
        except RedisError:
            logger.exception("Chat cache invalidation failed for updated visitor context.")

    return {
        "visitor_id": visitor_id,
        "name": name or cached_name or "",
        "init_touchpoint_id": touchpoint_id or cached_touchpoint or "",
        "cached": bool(redis_data),
        "error_code": 0
    }


@router.post("/_leoai/touchpoint/geolocation", response_class=JSONResponse)
@router.post("/touchpoint/geolocation", response_class=JSONResponse)
async def create_geolocation_touchpoint(
    payload: GeolocationTouchpointRequest,
):
    """Create/update a geolocation touchpoint and return nearby places."""
    result = await rag_agent.create_geolocation_touchpoint(
        payload.visitor_id.strip(),
        payload.latitude,
        payload.longitude,
        payload.touchpoint_id,
        payload.name,
        payload.description,
        payload.type,
        payload.keywords,
    )
    await asyncio.to_thread(
        REDIS_CLIENT.hset,
        payload.visitor_id.strip(), mapping={"touchpoint_id": result["touchpoint_id"]},
    )
    try:
        await chat_response_cache.invalidate_visitor(payload.visitor_id.strip())
    except RedisError:
        logger.exception("Chat cache invalidation failed after geolocation update.")
    result["recommended_actions"] = _build_recommended_actions(
        result.get("nearby_places", [])
    )
    return result
