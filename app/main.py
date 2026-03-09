from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.routers import repeated_questions, topic_weightage, mock_test, study_notes, revision_ranking
from app.database.mongodb import db
from app.config import settings

app = FastAPI(
    title="AI Microservices - PYQ Intelligence",
    description="AI-powered analysis of Previous Year Question Papers",
    version=settings.APP_VERSION,
)

# CORS — configurable via .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(repeated_questions.router, prefix="/api/v1", tags=["Feature 1: Smart Pattern Finder"])
app.include_router(topic_weightage.router, prefix="/api/v1", tags=["Feature 2: Exam Blueprint DNA"])
app.include_router(mock_test.router, prefix="/api/v1", tags=["Feature 3: Predictive AI Mock Test"])
app.include_router(revision_ranking.router, prefix="/api/v1", tags=["Feature 4: Emergency Pass Master"])
app.include_router(study_notes.router, prefix="/api/v1", tags=["Feature 5: AI Masterclass Notes"])


@app.get("/", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "AI-Microservices — PYQ Intelligence",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": [
            "Repeated Question Detection",
            "Topic Weightage Analysis",
            "Stratified Mock Test Generation",
            "Smart Study Notes Generator"
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
