import json
import re
import asyncio
from PIL import Image
import google.generativeai as genai
from datetime import datetime

from app.config import settings
from app.models.schemas import ExtractedQuestion
from app.logger import get_logger

logger = get_logger("question_extractor")

def _configure_genai():
    """Configure the Gemini API client."""
    genai.configure(api_key=settings.GEMINI_API_KEY)

def _clean_json_response(text: str) -> str:
    """Extract JSON from Gemini's response."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"(\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

async def extract_questions_from_images(
    images: list[Image.Image],
) -> list[ExtractedQuestion]:
    """
    Extract questions from PDF page images using Gemini Vision.
    Optimized: Sends all pages in a single batch request.
    Production-grade: uses async API + configurable retry from settings.
    """
    _configure_genai()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    logger.info(f"Starting OCR extraction for {len(images)} pages...")
    
    prompt = """You are an expert academic assistant. Extract ALL exam questions from the provided images.

RULES:
1. Extract the FULL question text including all sub-parts (a, b, c, etc.)
2. Include the question number as it appears on the paper.
3. If a question has "OR" between options, treat each option as a separate question.
4. IGNORE header info (university name, instructions, marks info).
5. IGNORE roll number fields and non-question content.

Return ONLY a valid JSON array of objects:
[{"questionNumber": "1", "questionText": "Full text of question 1"}]

If no questions are found, return an empty array []."""

    # Batch all images together with the prompt
    content = [prompt] + images

    for attempt in range(settings.GEMINI_MAX_RETRIES):
        try:
            start_time = datetime.now()
            response = await model.generate_content_async(content)
            raw_text = response.text
            cleaned = _clean_json_response(raw_text)
            questions_data = json.loads(cleaned)
            
            extracted = [
                ExtractedQuestion(
                    questionNumber=str(q.get("questionNumber", "")),
                    questionText=str(q.get("questionText", ""))
                )
                for q in questions_data if q.get("questionText")
            ]
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Extraction complete! Found {len(extracted)} questions in {duration:.1f}s.")
            return extracted

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower():
                wait_time = 10 * (attempt + 1)
                logger.warning(f"Rate limit hit. Retrying in {wait_time}s... (Attempt {attempt+1}/{settings.GEMINI_MAX_RETRIES})")
                await asyncio.sleep(wait_time)
            else:
                if attempt < settings.GEMINI_MAX_RETRIES - 1:
                    wait_time = settings.GEMINI_RETRY_DELAY * (attempt + 1)
                    logger.warning(f"OCR attempt {attempt+1} failed: {error_str[:100]}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"OCR extraction failed after {settings.GEMINI_MAX_RETRIES} attempts: {error_str[:300]}")
                    return []

    return []
