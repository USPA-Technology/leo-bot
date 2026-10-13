import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from leoai.rag_agent import RAGAgent
from leobot_router.leobot_request_filter import (
    RequestFilterUnavailable,
    filter_webhook_message,
)
from main_config import BASE_URL_FB_MSG, FB_PAGE_ACCESS_TOKEN, FB_VERIFY_TOKEN

# Facebook webhook router
logger = logging.getLogger("leobot-facebook")
router = APIRouter()
rag_agent = RAGAgent()


@router.get("/_leoai/fb-webhook", response_class=JSONResponse)
async def verify_fb_webhook(request: Request):
    """
    Facebook webhook verification endpoint.
    Used when setting up the Facebook app subscription.
    """
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == FB_VERIFY_TOKEN:
        logger.info("✅ FB Webhook verified.")
        return PlainTextResponse(params.get("hub.challenge"))
    logger.warning("❌ FB Webhook verification failed.")
    return JSONResponse(status_code=403, content={"error": "Verification failed"})


@router.post("/_leoai/fb-webhook", response_class=JSONResponse)
async def fb_webhook_handler(request: Request):
    """
    Handles incoming messages from Facebook Messenger users.
    Passes text to the RAGAgent for AI response.
    """
    try:
        body = await request.json()
        for entry in body.get("entry", []):
            for event in entry.get("messaging", []):
                sender = event.get("sender", {})
                sender_id = sender.get("id")
                user_msg = event.get("message", {}).get("text")
                if not sender_id or not user_msg:
                    continue
                filtered = filter_webhook_message(sender_id, user_msg)
                if filtered is None:
                    logger.warning("Rejected invalid or rate-limited Facebook message")
                    continue
                logger.info("FB user '%s' sent an accepted message", filtered.visitor_id)

                ai_reply = await rag_agent.process_chat_message(
                    user_id=filtered.visitor_id,
                    user_message=filtered.message,
                    persona_id="fb_user",
                    cdp_profile_id="",
                    touchpoint_id="facebook",
                    channel="facebook_messenger",
                )
                await send_message_to_facebook(sender_id, ai_reply)
    except RequestFilterUnavailable:
        logger.exception("Facebook chat rate-limit store is unavailable")
        return JSONResponse(status_code=503, content={"error": "Chat service unavailable"})
    except Exception:
        logger.exception("Error in FB webhook handler")
        return JSONResponse(status_code=500, content={"error": "Webhook processing failed"})
    return {"ok": True}


async def send_message_to_facebook(recipient_id: str, message_text: str):
    """
    Sends a text message reply to a Facebook Messenger user.
    """
    url = f"{BASE_URL_FB_MSG}?access_token={FB_PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"✅ Sent message to FB user {recipient_id}")
    except httpx.HTTPError:
        logger.exception("❌ Failed to send message to FB user %s", recipient_id)
