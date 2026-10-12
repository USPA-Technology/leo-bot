import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Local configuration
from main_config import RESOURCES_DIR, TEMPLATES_DIR, leobot_lifespan, setup_logging

# Inbound routers
from leobot_router.leobot_main_router import router as main_router
from leobot_router.leobot_assets_router import router as assets_router

# Outbound routers
from leobot_router.leobot_email_router import router as email_router
from leobot_router.leobot_facebook_router import router as facebook_router
from leobot_router.leobot_zalo_router import router as zalo_router
from leobot_router.leobot_knowledge_router import router as knowledge_router

# Admin (optional Keycloak)
from leobot_router.leobot_admin_router import keycloak_enabled, router as admin_router

# Logging setup
setup_logging()
logger = logging.getLogger("leobot_app")


def create_app() -> FastAPI:
    """Create and configure the LEO Bot FastAPI application."""
    app = FastAPI(lifespan=leobot_lifespan)

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],      # Allow all origins (change in prod)
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Static & Template Setup ---
    app.mount("/resources", StaticFiles(directory=RESOURCES_DIR), name="resources")
    app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # --- Router Registration ---
    routers = [
        main_router,
        assets_router,
        email_router,
        facebook_router,
        zalo_router,
        knowledge_router,
    ]
    for r in routers:
        app.include_router(r)

    # --- Conditional Admin Routes ---
    if keycloak_enabled:
        logger.info("🔐 Keycloak enabled → mounting admin routes.")
        app.include_router(admin_router)
    else:
        logger.warning("🚫 Keycloak disabled → skipping admin routes.")

    return app


# --- Entrypoint ---
leobot = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_app:leobot", host="0.0.0.0", port=8888, reload=True)