from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.routers import repeated_questions, topic_weightage, mock_test, study_notes, revision_ranking
from app.dependencies.auth import get_current_user
from app.database.mongodb import db
from app.config import settings

app = FastAPI(
    title="AI Microservices - PYQ Intelligence",
    description="AI-powered analysis of Previous Year Question Papers",
    version=settings.APP_VERSION,
)

# CORS — configurable via .env
# CORS — explicit for better safety and browser compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)

# Register routers (Secured with JWT)
auth_dep = [Depends(get_current_user)]

app.include_router(repeated_questions.router, prefix="/api/v1", tags=["Feature 1: Smart Pattern Finder"], dependencies=auth_dep)
app.include_router(topic_weightage.router, prefix="/api/v1", tags=["Feature 2: Exam Blueprint DNA"], dependencies=auth_dep)
app.include_router(mock_test.router, prefix="/api/v1", tags=["Feature 3: Predictive AI Mock Test"], dependencies=auth_dep)
app.include_router(revision_ranking.router, prefix="/api/v1", tags=["Feature 4: Emergency Pass Master"], dependencies=auth_dep)
app.include_router(study_notes.router, prefix="/api/v1", tags=["Feature 5: AI Masterclass Notes"], dependencies=auth_dep)


@app.get("/", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "AI-Microservices — PYQ Intelligence",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": [
            "Smart Pattern Finder",
            "Exam Blueprint DNA",
            "Predictive AI Mock Test",
            "Emergency Pass Master",
            "AI Masterclass Notes"
        ]
    }


@app.get("/api/v1/stats", tags=["System"])
async def get_system_stats():
    """Production dashboard: Shows library size, cached analyses, and subject coverage."""
    stats = await db.get_library_stats()
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": stats,
        "geminiModel": settings.GEMINI_MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
