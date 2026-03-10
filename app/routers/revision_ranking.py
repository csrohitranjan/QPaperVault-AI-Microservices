import asyncio
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from app.models.schemas import RevisionRankingRequest, RevisionRankingResponse
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.revision_ranking_service import generate_revision_ranking
from app.database.mongodb import db, generate_paper_fingerprint
from app.logger import get_logger
from app.dependencies.auth import get_current_user

router = APIRouter()
logger = get_logger("revision_ranking_router")

@router.post("/revision-ranking", response_model=RevisionRankingResponse)
async def get_revision_ranking(request: RevisionRankingRequest, auth_data: dict = Depends(get_current_user)):
    """
    Advanced Endpoint for Feature #4: One-Stop Revision Suite.
    Provides ranking, fast answers, diagrams, and pass-guarantee path.
    """
    start_time = datetime.now()
    token = auth_data["token"]
    logger.info(f"🚀 Request for Advanced Revision Guide: {request.paperCode} ({request.availableHours}h)")

    # 1. Fetch papers & fingerprint
    try:
        papers = await fetch_papers_by_code(request.paperCode, token)
    except Exception as e:
        logger.error(f"Failed to fetch papers for {request.paperCode}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch question papers.")

    if not papers:
        raise HTTPException(status_code=404, detail="No question papers found.")

    fingerprint = generate_paper_fingerprint(papers)

    # 2. Check Cache
    cache_key = f"emergency_pass_strategy_adv_{request.availableHours}h"
    cached_result = await db.get_cached_result(request.paperCode, cache_key, fingerprint)
    if cached_result:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"💎 [CACHE HIT] Advanced Revision Guide for {request.paperCode} served in {total_duration:.1f}s!")
        return RevisionRankingResponse(**cached_result["result_data"])

    # 3. Generate New Ranking
    ranking_data, dna_fingerprint = await generate_revision_ranking(request.paperCode, request.availableHours, token)
    if not ranking_data:
        raise HTTPException(status_code=500, detail="Failed to generate advanced revision ranking.")

    # 4. Prepare Response & Cache
    response_data = {
        "status": 200,
        "paperCode": request.paperCode,
        "paperName": papers[0].paperName,
        "urgencyRankings": ranking_data["urgencyRankings"],
        "mandatoryDefinitions": ranking_data.get("mandatoryDefinitions", []),
        "mandatoryDiagrams": ranking_data.get("mandatoryDiagrams", []),
        "passGuaranteeQuestions": ranking_data["passGuaranteeQuestions"],
        "cheatSheet": ranking_data["cheatSheet"]
    }

    metadata = {"paper_ids": [p.id for p in papers], "availableHours": request.availableHours, "isAdvanced": True}
    await db.save_to_cache(request.paperCode, cache_key, fingerprint, response_data, metadata)

    total_duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ Advanced Revision Guide for {request.paperCode} generated and cached in {total_duration:.1f}s!")

    return RevisionRankingResponse(**response_data)
