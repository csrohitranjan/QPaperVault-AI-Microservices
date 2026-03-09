import json
import re
import asyncio
import google.generativeai as genai
from datetime import datetime

from app.config import settings
from app.models.schemas import TopicWeightage
from app.logger import get_logger

logger = get_logger("topic_analyzer")

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

async def analyze_topics_from_questions(
    papers_data: list[dict],
) -> list[TopicWeightage]:
    """
    Analyze extracted questions and categorize them into meaningful academic topics.
    Then calculate the frequency and percentage weightage of each topic.
    Production-grade: uses async API + configurable retry.
    """
    if not papers_data:
        logger.warning("No question data provided for topic analysis.")
        return []

    _configure_genai()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    logger.info(f"Starting topic weightage analysis for {len(papers_data)} papers...")

    # Build a flat list of all questions
    all_questions = []
    for paper in papers_data:
        for q in paper.get("questions", []):
            if isinstance(q, dict):
                text = q.get("questionText", "")
            else:
                text = getattr(q, "questionText", "")
            if text:
                all_questions.append(text)

    if not all_questions:
        logger.warning("No readable question text found.")
        return []

    questions_block = "\n".join([f"- {q}" for q in all_questions])

    prompt = f"""You are an expert academic analysis system.
Below is a list of exam questions extracted from multiple years of the same subject.

YOUR TASK:
1. Identify the core academic TOPICS/CHAPTERS these questions belong to.
2. Categorize every single question into ONE of these topics.
3. Count how many questions belong to each topic.
4. Provide the result as a list of topics with their counts.

RULES:
- Limit the number of topics to between 5 and 10 to keep it concise.
- Use professional academic names for topics (e.g., 'Tree Data Structures' not just 'Trees').

QUESTIONS:
{questions_block}

Return ONLY a valid JSON array:
[
  {{
    "topicName": "Name of the Topic",
    "occurrenceCount": 12
  }}
]"""

    # Retry logic
    for attempt in range(settings.GEMINI_MAX_RETRIES):
        try:
            start_time = datetime.now()
            response = await model.generate_content_async(prompt)
            raw_text = response.text

            cleaned = _clean_json_response(raw_text)
            topic_data = json.loads(cleaned)

            total_questions = sum(item.get("occurrenceCount", 0) for item in topic_data)
            
            final_topics = []
            for item in topic_data:
                count = item.get("occurrenceCount", 0)
                percentage = (count / total_questions * 100) if total_questions > 0 else 0
                
                final_topics.append(
                    TopicWeightage(
                        topicName=item.get("topicName", "Unknown"),
                        occurrenceCount=count,
                        weightage=f"{percentage:.1f}%"
                    )
                )

            final_topics.sort(key=lambda t: t.occurrenceCount, reverse=True)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Topic analysis complete! Identified {len(final_topics)} topics in {duration:.1f}s.")
            
            return final_topics

        except Exception as e:
            if attempt < settings.GEMINI_MAX_RETRIES - 1:
                wait_time = settings.GEMINI_RETRY_DELAY * (attempt + 1)
                logger.warning(f"Topic analysis attempt {attempt+1} failed: {str(e)[:100]}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Topic analysis failed after {settings.GEMINI_MAX_RETRIES} attempts: {str(e)[:300]}")
                return []
