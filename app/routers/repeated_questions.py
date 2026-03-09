import asyncio
from fastapi import APIRouter, HTTPException
from datetime import datetime

from app.models.schemas import RepeatedQuestionsRequest, RepeatedQuestionsResponse, PaperInfo
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.paper_processor import process_single_paper
from app.services.similarity_analyzer import analyze_similar_questions
from app.logger import get_logger
from app.database.mongodb import db, generate_paper_fingerprint

router = APIRouter()
logger = get_logger("repeated_questions_router")

@router.post("/repeated-questions", response_model=RepeatedQuestionsResponse)
async def get_repeated_questions(request: RepeatedQuestionsRequest):
    """
    Feature #1: Repeated Question Detection with Two-Layer Caching.
    Layer 2: Instant Feature Result
    Layer 1: Permanent Paper Library
    """
    start_time = datetime.now()
    logger.info(f"🚀 Request for {request.paperCode}")

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
    cached_result = await db.get_cached_result(request.paperCode, "smart_pattern_analysis", fingerprint)
    if cached_result:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"💎 [CACHE HIT] Result for {request.paperCode} served in {total_duration:.1f}s!")
        return RepeatedQuestionsResponse(**cached_result["result_data"])

    # 3. Process Papers (Layer 1 Integration)
    # This will check the Library for each paper individually.
    logger.info(f"Processing {len(papers)} papers using Library sync...")
    tasks = [process_single_paper(paper) for paper in papers]
    results = await asyncio.gather(*tasks)
    valid_results = [r for r in results if r is not None]

    if not valid_results:
        raise HTTPException(status_code=500, detail="Failed to extract questions from papers.")

    # 4. Analyze similarity
    logger.info(f"Analyzing similarity across extracted questions...")
    repeated_questions = await analyze_similar_questions(valid_results)

    # 5. Prepare Response and Save to Analysis Cache (Layer 2)
    response_data = {
        "status": 200,
        "paperCode": request.paperCode,
        "paperName": papers[0].paperName,
        "totalPapersAnalyzed": len(valid_results),
        "repeatedQuestions": [q.model_dump() for q in repeated_questions]
    }

    metadata = {"paper_ids": [p.id for p in papers]}
    await db.save_to_cache(request.paperCode, "smart_pattern_analysis", fingerprint, response_data, metadata)

    total_duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ Analysis for {request.paperCode} complete and cached in {total_duration:.1f}s!")

    return RepeatedQuestionsResponse(**response_data)
