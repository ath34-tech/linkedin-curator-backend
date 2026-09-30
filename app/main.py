import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.models.database import init_db
from app.services.scheduler import init_scheduler, shutdown_scheduler
from app.services.ocr import UPLOADS_DIR
from app.routes import (
    ideas_router,
    knowledge_router,
    notes_router,
    projects_router,
    learning_router,
    trends_router,
    sources_router,
    settings_router
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ATH-Radar")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Initializing ATH Radar Database...")
    init_db()

    # Sync persistent settings from DB into services
    from app.routes.settings import sync_settings_from_db
    sync_settings_from_db()

    logger.info("Starting Scheduler...")
    init_scheduler()

    yield

    # Shutdown actions
    logger.info("Shutting down ATH Radar...")
    shutdown_scheduler()

app = FastAPI(
    title="ATH Radar API",
    description="Personal AI-Powered Content Intelligence Engine for ATH",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for React Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded note images
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# Include API Routers
app.include_router(ideas_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(learning_router, prefix="/api")
app.include_router(trends_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(settings_router, prefix="/api")

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "ATH Radar API",
        "scheduler_active": settings.ENABLE_SCHEDULER
    }
