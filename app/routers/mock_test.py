import asyncio
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from app.models.schemas import MockTestRequest, MockTestResponse
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.mock_generator import generate_stratified_mock_test
from app.database.mongodb import db, generate_paper_fingerprint
from app.logger import get_logger
from app.dependencies.auth import get_current_user

router = APIRouter()
logger = get_logger("mock_test_router")

@router.post("/generate-mock-test", response_model=MockTestResponse)
async def generate_mock_test(request: MockTestRequest, auth_data: dict = Depends(get_current_user)):
    """
    Endpoint for Feature #3: Stratified Mock Test Generation.
    Uses Layered Cache and Exam DNA.
    """
    start_time = datetime.now()
    token = auth_data["token"]
    logger.info(f"🚀 Request for Mock Test: {request.paperCode}")

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
    cached_result = await db.get_cached_result(request.paperCode, "predictive_ai_test", fingerprint)
    if cached_result:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"💎 [CACHE HIT] Mock Test for {request.paperCode} served in {total_duration:.1f}s!")
        return MockTestResponse(**cached_result["result_data"])

    # 3. Generate New Mock Test
    result = await generate_stratified_mock_test(request.paperCode, request.totalMarks, token)
    if not result:
        raise HTTPException(status_code=400, detail="Topic DNA analysis not found for this subject. Please run Topic Weightage analysis first.")
    
    test_data, dna_fingerprint = result

    # 4. Prepare Response & Cache
    response_data = {
        "status": 200,
        "paperCode": request.paperCode,
        "paperName": papers[0].paperName,
        "totalMarks": request.totalMarks,
        "examDNAUsed": dna_fingerprint,
        "testStructure": test_data["testStructure"]
    }

    metadata = {"paper_ids": [p.id for p in papers], "totalMarks": request.totalMarks}
    await db.save_to_cache(request.paperCode, "predictive_ai_test", fingerprint, response_data, metadata)

    total_duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ Mock Test for {request.paperCode} generated and cached in {total_duration:.1f}s!")

    return MockTestResponse(**response_data)
