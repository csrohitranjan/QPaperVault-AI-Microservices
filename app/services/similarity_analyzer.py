import json
import re
import asyncio
import google.generativeai as genai
from datetime import datetime

from app.config import settings
from app.models.schemas import (
    PaperWithQuestions,
    RepeatedQuestion,
    QuestionOccurrence,
)
from app.logger import get_logger

logger = get_logger("similarity_analyzer")

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

async def analyze_similar_questions(
    papers_data: list[dict],
) -> list[RepeatedQuestion]:
    """
    Analyze questions across multiple papers and identify repeated /
    semantically similar questions using Gemini LLM.
    Production-grade: uses async API + configurable retry.
    """
    if len(papers_data) < 2:
        logger.warning("Not enough papers (min 2) for similarity analysis.")
        return []

    _configure_genai()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    logger.info(f"Starting similarity analysis for {len(papers_data)} papers...")

    # Build a structured input of all questions organized by paper year/month
    all_questions_text = ""
    for paper in papers_data:
        all_questions_text += f"\n--- Paper: {paper['month']} {paper['year']} ---\n"
        for q in paper["questions"]:
            all_questions_text += f"  Q{q.get('questionNumber', '')}: {q.get('questionText', '')}\n"

    prompt = f"""You are an expert academic analysis system.
Below are questions extracted from multiple years of the SAME subject exam paper.
Identify questions that are REPEATED or VERY SIMILAR across different years.

RULES:
1. "Similar" means the SAME concept/topic, even if worded differently.
2. Provide ONE clear representative version of the question.
3. Only include questions that appear in 2 or MORE papers.
4. Sort by frequency — highest first.

QUESTIONS FROM ALL PAPERS:
{all_questions_text}

Return ONLY a valid JSON array:
[
  {{
    "question": "Representative question text",
    "frequency": 3,
    "appearedIn": [
      {{"year": 2025, "month": "APR-MAY"}},
      {{"year": 2024, "month": "NOV-DEC"}}
    ]
  }}
]

If no repeats, return []."""

    # Retry logic
    for attempt in range(settings.GEMINI_MAX_RETRIES):
        try:
            start_time = datetime.now()
            response = await model.generate_content_async(prompt)
            raw_text = response.text

            cleaned = _clean_json_response(raw_text)
            repeated_data = json.loads(cleaned)

            repeated_questions = []
            for item in repeated_data:
                occurrences = [
                    QuestionOccurrence(
                        year=occ.get("year", 0),
                        month=occ.get("month", ""),
                    )
                    for occ in item.get("appearedIn", [])
                ]

                repeated_questions.append(
                    RepeatedQuestion(
                        question=item.get("question", ""),
                        frequency=item.get("frequency", len(occurrences)),
                        appearedIn=occurrences,
                    )
                )

            repeated_questions.sort(key=lambda q: q.frequency, reverse=True)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Similarity analysis complete! Identified {len(repeated_questions)} repeated groups in {duration:.1f}s.")
            
            return repeated_questions

        except Exception as e:
            if attempt < settings.GEMINI_MAX_RETRIES - 1:
                wait_time = settings.GEMINI_RETRY_DELAY * (attempt + 1)
                logger.warning(f"Similarity analysis attempt {attempt+1} failed: {str(e)[:100]}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Similarity analysis failed after {settings.GEMINI_MAX_RETRIES} attempts: {str(e)[:300]}")
                return []
