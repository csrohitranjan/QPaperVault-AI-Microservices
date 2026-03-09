import asyncio
from app.models.schemas import PaperInfo
from app.services.pdf_processor import download_pdf, pdf_to_images
from app.services.question_extractor import extract_questions_from_images
from app.database.mongodb import db
from app.logger import get_logger

logger = get_logger("paper_processor")

async def process_single_paper(paper: PaperInfo):
    """
    Unified workflow for processing a single paper with Per-Paper Library (Layer 1) support.
    Checks the MongoDB Paper Library before performing OCR.
    """
    paper_id = paper.id
    paper_label = f"{paper.year} {paper.month}"
    try:
        # 1. Check Library (Layer 1)
        cached_ocr = await db.get_paper_ocr(paper_id)
        if cached_ocr:
            logger.info(f"📚 [LIBRARY HIT] Using cached OCR for {paper.paperName} ({paper_label})")
            return {
                "questions": cached_ocr["questions"],
                "year": paper.year,
                "month": paper.month
            }

        # 2. If MISS, perform full extraction
        logger.info(f"🚀 [LIBRARY MISS] Extracting paper: {paper.paperName} ({paper_label})...")
        
        pdf_bytes = await download_pdf(paper.fileUrl)
        images = pdf_to_images(pdf_bytes)
        questions = await extract_questions_from_images(images)
        
        # 3. Save to Library (Layer 1)
        questions_data = [q.model_dump() for q in questions]
        paper_metadata = {
            "paperName": paper.paperName,
            "paperCode": paper.paperCode,
            "year": paper.year,
            "month": paper.month,
            "department": paper.department,
            "programme": paper.programme
        }
        await db.save_paper_ocr(paper_id, questions_data, paper_metadata)
        
        return {
            "questions": questions_data,
            "year": paper.year,
            "month": paper.month
        }
    except Exception as e:
        logger.error(f"Failed to process {paper_label}: {str(e)[:200]}")
        return None
