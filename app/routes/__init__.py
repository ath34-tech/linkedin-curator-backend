from app.routes.ideas import router as ideas_router
from app.routes.knowledge import router as knowledge_router
from app.routes.notes import router as notes_router
from app.routes.projects import router as projects_router
from app.routes.learning import router as learning_router
from app.routes.trends import router as trends_router
from app.routes.sources import router as sources_router
from app.routes.settings import router as settings_router

__all__ = [
    "ideas_router",
    "knowledge_router",
    "notes_router",
    "projects_router",
    "learning_router",
    "trends_router",
    "sources_router",
    "settings_router"
]
