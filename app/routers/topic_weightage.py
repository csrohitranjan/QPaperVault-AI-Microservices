import asyncio
from fastapi import APIRouter, HTTPException
from datetime import datetime

from app.models.schemas import TopicAnalysisRequest, TopicAnalysisResponse, PaperInfo
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.paper_processor import process_single_paper
from app.services.topic_analyzer import analyze_topics_from_questions
from app.database.mongodb import db, generate_paper_fingerprint
from app.logger import get_logger

router = APIRouter()
logger = get_logger("topic_weightage_router")

@router.post("/topic-weightage", response_model=TopicAnalysisResponse)
async def get_topic_weightage(request: TopicAnalysisRequest):
    """
    Endpoint for Feature #2: Topic Weightage Analysis.
    Smart implementation: Reuses cached OCR data from Feature 1 if available.
    """
    start_time = datetime.now()
    logger.info(f"🚀 Starting topic analysis for paperCode: {request.paperCode}")

    # 1. Fetch papers & generate fingerprint
    try:
        papers = await fetch_papers_by_code(request.paperCode)
    except Exception as e:
        logger.error(f"Failed to fetch papers for {request.paperCode}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch question papers.")

    if not papers:
        raise HTTPException(status_code=404, detail="No question papers found.")

    fingerprint = generate_paper_fingerprint(papers)

    # 2. Check Cache
    cached_result = await db.get_cached_result(request.paperCode, "exam_blueprint_dna", fingerprint)
    if cached_result:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"💎 [CACHE HIT] Topic analysis for {request.paperCode} served in {total_duration:.1f}s!")
        return TopicAnalysisResponse(**cached_result["result_data"])

    # 3. Process Papers (Layer 1 Integration)
    # This will check the Library for each paper individually.
    logger.info(f"Processing {len(papers)} papers using Library sync...")
    tasks = [process_single_paper(paper) for paper in papers]
    extraction_results = await asyncio.gather(*tasks)
    extraction_results = [r for r in extraction_results if r is not None]

    if not extraction_results:
        raise HTTPException(status_code=500, detail="Failed to extract questions.")

    # 4. Analyze Topics
    topics = await analyze_topics_from_questions(extraction_results)

    # 5. Prepare Response & Cache
    response_data = {
        "status": 200,
        "paperCode": request.paperCode,
        "paperName": papers[0].paperName,
        "totalPapersAnalyzed": len(extraction_results),
        "topics": [t.model_dump() for t in topics]
    }

    # Meta-data for the cache
    metadata = {"paper_ids": [p.id for p in papers]}

    await db.save_to_cache(request.paperCode, "exam_blueprint_dna", fingerprint, response_data, metadata)

    total_duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ Topic analysis for {request.paperCode} complete and cached in {total_duration:.1f}s!")

    return TopicAnalysisResponse(**response_data)
