import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from redis import Redis
from fastapi import FastAPI
from leoai.ai_core import get_embedding_model
import logging

# Load environment variables from .env file
load_dotenv(override=True)

# --- General ---
VERSION = "1.0.0"
SERVICE_NAME = f"LEO BOT VERSION: {VERSION}"
LEOBOT_DEV_MODE = os.getenv("LEOBOT_DEV_MODE") == "true"
HOSTNAME = os.getenv("HOSTNAME", "localhost")

# --- Rate Limiting ---
RATE_LIMIT_MAX_MESSAGES = 20  # max messages
RATE_LIMIT_WINDOW_SECONDS = 60  # time window

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_USER_SESSION_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_USER_SESSION_PORT", 6379))
REDIS_CLIENT = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# --- Facebook Integration ---
BASE_URL_FB_MSG = 'https://graph.facebook.com/v13.0/me/messages'
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
FB_VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN")

# --- Gemini API ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Zalo OA Token ---
ZALO_OA_ACCESS_TOKEN = os.getenv("ZALO_OA_ACCESS_TOKEN")

# --- File Paths ---
BASE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = BASE_DIR / "resources"
TEMPLATES_DIR = RESOURCES_DIR / "templates"

# logging
logging.basicConfig(level=logging.INFO)

# lifespan of FastAPI app
@asynccontextmanager
async def leobot_lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)
    # Startup logic
    logger.info("🔄 Initializing LEO BOT and loading configs ...")
    logger.info(f" HOSTNAME: {HOSTNAME}")
    logger.info(f" LEOBOT_DEV_MODE: {LEOBOT_DEV_MODE}")
    
    # start some base services for caching
    get_embedding_model()
    
    # App runs here
    yield  
    
    # Shutdown logic
    logger.info("🛑 Shutting down LEO BOT ...")