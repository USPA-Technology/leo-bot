import os
import time
import json
import logging
import urllib3
import httpx
from uuid6 import uuid7
from dotenv import load_dotenv
from fastapi import APIRouter, Query, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi_keycloak import FastAPIKeycloak
from fastapi_keycloak.exceptions import KeycloakError
from main_config import HOSTNAME, LEOBOT_DEV_MODE, TEMPLATES_DIR, REDIS_CLIENT

# ------------------------------------------------------------------------------
# Setup & Config
# ------------------------------------------------------------------------------
logger = logging.getLogger("leobot-admin")
load_dotenv(override=True)

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

keycloak_enabled = os.getenv("KEYCLOAK_ENABLED", "false").lower() in {"true", "1", "yes"}
verify_ssl = os.getenv("KEYCLOAK_VERIFY_SSL", "true").lower() not in {"false", "0", "no"}

if not verify_ssl:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

keycloak_openid = None

# ------------------------------------------------------------------------------
# Keycloak Initialization (FIXED)
# ------------------------------------------------------------------------------
if keycloak_enabled:
    try:
        # --- FIX START ---
        # Load the client secret from the environment.
        # This is required for a "confidential client" (Client authentication: On).
        client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
        if not client_secret:
            # Fail fast if the secret is missing, as Keycloak will reject auth.
            raise ValueError("KEYCLOAK_CLIENT_SECRET is not set in environment.")
        # --- FIX END ---
        
        # This lambda prevents the library from trying to get an admin token,
        # which we don't need for this simple OpenID Connect flow.
        FastAPIKeycloak._get_admin_token = lambda *_, **__: None
        
        keycloak_openid = FastAPIKeycloak(
            server_url=os.getenv("KEYCLOAK_URL"),
            realm=os.getenv("KEYCLOAK_REALM"),
            client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
            callback_uri=os.getenv("KEYCLOAK_CALLBACK_URL"),
            ssl_verification=verify_ssl,
            timeout=10,
            
            # --- FIX ---
            # Pass the loaded secret to the constructor.
            # Setting this to None (as before) makes it a "public client"
            # and will cause a mismatch with Keycloak's settings.
            client_secret=client_secret,
            # --- END FIX ---
            
            admin_client_secret=None,
        )
        
        # Updated log message to reflect the correct client type
        logger.info("✅ Keycloak initialized (confidential client + Redis mode).")
        
    except Exception as e:
        logger.exception(f"❌ Keycloak initialization failed: {e}")
else:
    logger.warning("🚫 Keycloak disabled via environment.")

# ------------------------------------------------------------------------------
# Redis session helpers
# ------------------------------------------------------------------------------
def create_redis_session(user_info: dict, token: dict) -> str:
    """Store user info + token in Redis, return session ID."""
    session_id = f"sid:{uuid7()}"
    data = json.dumps(
        {"user": user_info, "token": token, "timestamp": int(time.time())}
    )
    REDIS_CLIENT.setex(session_id, 3600, data)  # 1-hour TTL
    logger.info(f"💾 Created Redis session {session_id} for {user_info.get('preferred_username')}")
    return session_id


def get_session_from_redis(session_id: str):
    """Retrieve session data from Redis."""
    data = REDIS_CLIENT.get(session_id)
    return json.loads(data) if data else None



async def get_user_info_from_token(access_token: str) -> dict:
    """
    Fetch user info via Keycloak's REST API using httpx,
    with verbose debugging for troubleshooting Keycloak and network issues.
    """
    realm = os.getenv("KEYCLOAK_REALM")
    server_url = os.getenv("KEYCLOAK_URL")
    userinfo_url = f"{server_url}/realms/{realm}/protocol/openid-connect/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}

    logger.debug(f"[SSO] Fetching user info from: {userinfo_url}")
    logger.debug(f"[SSO] Using access token prefix: {access_token[:20]}...")

    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10) as client:
            resp = await client.get(userinfo_url, headers=headers)

        logger.debug(f"[SSO] HTTP status: {resp.status_code}")
        logger.debug(f"[SSO] Raw response: {resp.text}")

        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"[SSO] ✅ Retrieved user info for: {data.get('preferred_username')}")
            return data
        elif resp.status_code == 401:
            logger.error(f"[SSO] ❌ Unauthorized: invalid or expired access token")
        else:
            logger.error(f"[SSO] ❌ Unexpected response {resp.status_code}: {resp.text}")
        return {}

    except httpx.TimeoutException:
        logger.exception("[SSO] ⏱️ Timeout while contacting Keycloak userinfo endpoint")
        return {}
    except httpx.RequestError as e:
        logger.exception(f"[SSO] 🌐 Network error: {e}")
        return {}
    except json.JSONDecodeError:
        logger.exception("[SSO] 🧩 Failed to decode JSON from Keycloak response")
        return {}
    except Exception as e:
        logger.exception(f"[SSO] ⚠️ Unexpected error while fetching user info: {e}")
        return {}


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@router.get("/_leoai/is-admin-ready", response_class=JSONResponse)
async def is_ready():
    """Simple Keycloak health indicator."""
    return {"ok": keycloak_openid is not None}


# ------------------------------------------------------------------------------
# Authenticated Routes
# ------------------------------------------------------------------------------
if keycloak_openid:

    
    @router.get("/_leoai/sso/error", response_class=HTMLResponse)
    async def sso_error(
        request: Request,
        error: str = Query("unknown", description="Error type from Keycloak or SSO flow"),
        description: str = Query("", description="Optional error details"),
    ):
        """Display or return structured SSO error information."""
        # Mapping known errors to human-friendly messages
        error_map = {
            "invalid_grant": "Invalid or expired authorization code. Please log in again.",
            "unauthorized_client": "The Keycloak client configuration is invalid or missing permissions.",
            "userinfo_fetch_failed": "Unable to retrieve user profile from Keycloak.",
            "server_error": "Internal server error during SSO callback.",
            "unknown": "An unknown SSO error occurred.",
        }

        message = error_map.get(error, error_map["unknown"])
        logger.warning(f"🔁 SSO error occurred: {error} → {message}")

        # Detect if request is API (e.g. AJAX/fetch) or browser
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return JSONResponse(
                status_code=400,
                content={
                    "error": error,
                    "message": message,
                    "description": description,
                    "timestamp": int(time.time()),
                },
            )

        # Browser request → render simple error page
        context = {
            "request": request,
            "error": error,
            "message": message,
            "description": description,
            "timestamp": int(time.time()),
        }
        return templates.TemplateResponse(request, "admin/sso_error.html", context, status_code=400)
    
    @router.get("/_leoai/sso/login")
    async def login():
        """Redirect to Keycloak login page."""
        return RedirectResponse(url=keycloak_openid.login_uri)
    

    @router.get("/_leoai/sso/callback", response_class=HTMLResponse)
    async def sso_callback(
        request: Request,
        code: str | None = Query(None),
        session_state: str | None = Query(None),
        error: str | None = Query(None),
        error_description: str | None = Query(None),
        iss: str | None = Query(None),
        logout: str | None = Query(None),
    ):
        """
        Handle Keycloak callback, store session in Redis, and redirect.
        Supports both successful and error responses from Keycloak.
        """
        
        # 1. check logout first
        if logout == 'true':
            logger.error("[SSO] Logout OK!")
            return RedirectResponse(
                url=f"/admin?_t={int(time.time())}",
                status_code=303,
            )

        # 2. Handle error from Keycloak (e.g., expired, invalid, unavailable)
        if error:
            logger.warning(f"[SSO] Callback error: {error} → {error_description}")
            # Redirect user to your existing error page with full details
            return RedirectResponse(
                url=f"/_leoai/sso/error?error={error}&description={error_description or ''}",
                status_code=303,
            )

        # 3. Validate required parameters
        if not code or not session_state:
            logger.error("[SSO] Missing required params in callback (code/session_state).")
            return RedirectResponse(
                url="/_leoai/sso/error?error=invalid_grant&description=Missing+authorization+parameters",
                status_code=303,
            )
        
        try:
            # 4. Exchange authorization code for token
            token = keycloak_openid.exchange_authorization_code(
                session_state=session_state, code=code
            )
            access_token = token.access_token
            token_data = token.model_dump()

            # 5. Retrieve user info
            user_info = await get_user_info_from_token(access_token)
            if not user_info:
                logger.error("[SSO] Failed to fetch user info after successful token exchange.")
                return RedirectResponse(
                    url="/_leoai/sso/error?error=userinfo_fetch_failed",
                    status_code=303,
                )

            # 6. Create Redis session
            session_id = create_redis_session(user_info, token_data)

            # 7. Redirect to admin
            return RedirectResponse(url=f"/admin?sid={session_id}", status_code=303)

        except KeycloakError as e:
            logger.error(f"[SSO] Token exchange failed: {e}")
            return RedirectResponse(url="/_leoai/sso/error?error=invalid_grant", status_code=303)

        except Exception as e:
            logger.exception(f"[SSO] Unexpected callback error: {e}")
            return RedirectResponse(url="/_leoai/sso/error?error=server_error", status_code=303)


    @router.get("/admin", response_class=HTMLResponse)
    async def admin_panel(request: Request, sid: str = None, authorization: str = Header(None)):
        """Render admin dashboard using Redis session."""
        
        # Allow session ID to be passed as a query param (after login)
        # or as a Bearer token (for API calls)
        session_id = sid or (authorization.split("Bearer ")[-1] if authorization else None)
        
        if not session_id:
            # No session ID, must log in.
            return RedirectResponse(url="/_leoai/sso/login")

        session_data = get_session_from_redis(session_id)
        if not session_data:
            # Session ID is invalid or expired.
            return RedirectResponse(url="/_leoai/sso/login?expired=true")

        user = session_data["user"]
        context = {
            "request": request,
            "HOSTNAME": HOSTNAME,
            "LEOBOT_DEV_MODE": LEOBOT_DEV_MODE,
            "timestamp": int(time.time()),
            "user": {
                "username": user.get("preferred_username"),
                "email": user.get("email"),
                "name": user.get("name"),
            },
            # Pass the session ID to the template so it can be used for API calls
            "session_id": session_id 
        }
        return templates.TemplateResponse(request, "admin/dashboard.html", context)

    @router.get("/_leoai/sso/me", response_class=JSONResponse)
    async def get_me(sid: str = None, authorization: str = Header(None)):
        """Return current user info based on Redis session."""
        session_id = sid or (authorization.split("Bearer ")[-1] if authorization else None)
        if not session_id:
            raise HTTPException(status_code=401, detail="Missing session ID")

        session_data = get_session_from_redis(session_id)
        if not session_data:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        return {"user": session_data["user"], "session_id": session_id}

    @router.get("/_leoai/sso/logout")
    async def logout(request: Request, sid: str = None, authorization: str = Header(None)):
        """
        Invalidate Redis session AND logout from Keycloak (global SSO logout).
        """
        session_id = sid or (authorization.split("Bearer ")[-1] if authorization else None)
        keycloak_url = os.getenv("KEYCLOAK_URL")
        realm = os.getenv("KEYCLOAK_REALM")
        client_id = os.getenv("KEYCLOAK_CLIENT_ID")
        logout_callback_url = os.getenv("KEYCLOAK_CALLBACK_URL") + "?logout=true"

        # 1. Clear local Redis session
        if session_id:
            REDIS_CLIENT.delete(session_id)
            logger.info(f"🗑️ Session {session_id} invalidated locally.")

        # 2. Build Keycloak logout URL (end_session_endpoint)
        # Keycloak’s standard endpoint:
        #   /realms/{realm}/protocol/openid-connect/logout
        logout_url = (
            f"{keycloak_url}/realms/{realm}/protocol/openid-connect/logout"
            f"?client_id={client_id}&post_logout_redirect_uri={logout_callback_url}"
        )

        # Optional: If you stored the user's refresh_token in Redis, send it for full revocation:
        # logout_url += f"&refresh_token={refresh_token}"

        logger.info(f"🔒 Redirecting user to Keycloak logout at: {logout_url}")

        # 3. Redirect the browser to Keycloak for global logout
        return RedirectResponse(url=logout_url, status_code=303)



# ------------------------------------------------------------------------------
# Fallback if Keycloak disabled
# ------------------------------------------------------------------------------
else:

    @router.get("/admin", response_class=HTMLResponse)
    async def admin_panel_disabled(request: Request):
        return templates.TemplateResponse(
            request,
            "admin/error.html",
            {"request": request, "error_message": "Keycloak not enabled or failed to initialize."},
            status_code=503,
        )

    @router.get("/_leoai/sso/login")
    async def login_disabled():
        return JSONResponse(status_code=503, content={"error": "Keycloak not configured"})

    @router.get("/_leoai/sso/logout")
    async def logout_disabled():
        return RedirectResponse(url="/")