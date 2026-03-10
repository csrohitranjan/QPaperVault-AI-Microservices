import asyncio
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from app.models.schemas import StudyNotesRequest, StudyNotesResponse
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.study_notes_generator import generate_study_notes
from app.database.mongodb import db, generate_paper_fingerprint
from app.logger import get_logger
from app.dependencies.auth import get_current_user

router = APIRouter()
logger = get_logger("study_notes_router")

@router.post("/study-notes", response_model=StudyNotesResponse)
async def get_study_notes(request: StudyNotesRequest, auth_data: dict = Depends(get_current_user)):
    """
    Endpoint for Feature #5: Smart Study Notes Generator (Enhanced).
    Generates topic-wise study notes with model answers, predicted questions,
    and exam strategies using data from Features 1, 2, and Layer 1.
    """
    start_time = datetime.now()
    token = auth_data["token"]
    logger.info(f"🚀 Request for Study Notes: {request.paperCode}")

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
    cached_result = await db.get_cached_result(request.paperCode, "ai_masterclass_content", fingerprint)
    if cached_result:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"💎 [CACHE HIT] Study Notes for {request.paperCode} served in {total_duration:.1f}s!")
        return StudyNotesResponse(**cached_result["result_data"])

    # 3. Generate New Study Notes
    notes_data, dna_fingerprint, paper_count = await generate_study_notes(request.paperCode, token)
    if not notes_data:
        raise HTTPException(status_code=500, detail="Failed to generate study notes. Ensure Features 1 & 2 have been run.")

    # 4. Prepare Response & Cache
    response_data = {
        "status": 200,
        "paperCode": request.paperCode,
        "paperName": papers[0].paperName,
        "totalTopics": len(notes_data["studyNotes"]),
        "totalPapersAnalyzed": paper_count,
        "studyNotes": notes_data["studyNotes"],
        "predictedQuestions": notes_data.get("predictedQuestions", []),
        "quickRevisionSummary": notes_data["quickRevisionSummary"]
    }

    metadata = {"paper_ids": [p.id for p in papers]}
    await db.save_to_cache(request.paperCode, "ai_masterclass_content", fingerprint, response_data, metadata)

    total_duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ Study Notes for {request.paperCode} generated and cached in {total_duration:.1f}s!")

    return StudyNotesResponse(**response_data)
