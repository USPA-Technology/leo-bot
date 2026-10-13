import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from leoai.rag_agent import RAGAgent
from leobot_router.leobot_request_filter import (
    RequestFilterUnavailable,
    filter_webhook_message,
)
from main_config import ZALO_OA_ACCESS_TOKEN

# Zalo webhook router
logger = logging.getLogger("leobot-zalo")
router = APIRouter()
rag_agent = RAGAgent()


@router.post("/_leoai/zalo-webhook", response_class=JSONResponse)
async def zalo_webhook_handler(request: Request):
    """
    Zalo Official Account webhook for receiving messages.
    Processes text events and replies with AI-generated messages.
    """
    try:
        body = await request.json()
        event_name = body.get("event_name")

        if event_name == "user_send_text":
            user_id = body.get("sender", {}).get("id")
            user_msg = body.get("message", {}).get("text")
            if not user_id or not user_msg:
                return {"ok": True}
            filtered = filter_webhook_message(user_id, user_msg)
            if filtered is None:
                logger.warning("Rejected invalid or rate-limited Zalo message")
                return {"ok": True}
            logger.info("Zalo user '%s' sent an accepted message", filtered.visitor_id)

            ai_reply = await rag_agent.process_chat_message(
                user_id=filtered.visitor_id,
                user_message=filtered.message,
                persona_id="zalo_user",
                cdp_profile_id="",
                touchpoint_id="zalo",
                channel="zalo_oa",
            )
            await send_message_to_zalo(user_id, ai_reply)
    except RequestFilterUnavailable:
        logger.exception("Zalo chat rate-limit store is unavailable")
        return JSONResponse(status_code=503, content={"error": "Chat service unavailable"})
    except Exception:
        logger.exception("Error in Zalo webhook handler")
        return JSONResponse(status_code=500, content={"error": "Webhook processing failed"})

    return {"ok": True}


async def send_message_to_zalo(recipient_id: str, message_text: str):
    """
    Sends a message to a Zalo user via the OA API.
    """
    url = "https://openapi.zalo.me/v3.0/oa/message/cs"
    params = {"access_token": ZALO_OA_ACCESS_TOKEN}
    payload = {"recipient": {"user_id": recipient_id}, "message": {"text": message_text}}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(url, params=params, json=payload)
            res.raise_for_status()
            data = res.json()
            if data.get("error") == 0:
                logger.info(f"✅ Sent message to Zalo user {recipient_id}")
            else:
                logger.warning(f"⚠️ Zalo API returned error: {data}")
    except httpx.HTTPError:
        logger.exception("❌ Failed to send Zalo message to %s", recipient_id)
