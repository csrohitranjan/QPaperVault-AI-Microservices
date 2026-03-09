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

    # Build a structured block of questions categorized by year/month for trend analysis
    structured_questions = ""
    for paper in papers_data:
        paper_header = f"\n--- {paper.get('month', 'Unknown')} {paper.get('year', 'Unknown')} ---\n"
        structured_questions += paper_header
        for q in paper.get("questions", []):
            if isinstance(q, dict):
                text = q.get("questionText", "")
            else:
                text = getattr(q, "questionText", "")
            if text:
                structured_questions += f"- {text}\n"

    if not structured_questions:
        logger.warning("No readable question text found.")
        return []

    prompt = f"""You are an elite academic data scientist.
Below is a chronological list of exam questions extracted from several years of the same subject.

YOUR MISSION:
Perform a deep "Exam Blueprint DNA" analysis. Categorize questions into core topics and extract high-value metadata for each.

CHRONOLOGICAL QUESTIONS:
{structured_questions}

OUTPUT REQUIREMENTS (JSON Array of Objects):
1. 'topicName': Professional academic name (e.g., 'Concurrency & Multithreading').
2. 'occurrenceCount': Total count across all provided papers.
3. 'trend': Analyze frequency over the years. Is it 'Rising', 'Stable', or 'Falling'?
4. 'difficulty': Overall complexity of questions in this topic ('Easy', 'Moderate', 'Hard').
5. 'priority': Study priority (1-5, where 1 is "Must-Read / High Yield").
6. 'keyConcepts': Top 3-5 specific sub-concepts or technical keywords.
7. 'sampleQuestions': 2-3 short, representative questions from the provided list.

RULES:
- Limit to 6-10 most significant topics.
- Ensure 'weightage' can be calculated from 'occurrenceCount'.
- Return ONLY valid JSON.

JSON FORMAT EXAMPLE:
[
  {{
    "topicName": "Memory Management",
    "occurrenceCount": 15,
    "trend": "Rising",
    "difficulty": "Hard",
    "priority": 1,
    "keyConcepts": ["Garbage Collection", "Heap vs Stack", "Memory Leaks"],
    "sampleQuestions": ["Explain the lifecycle of an object in Java.", "What is the difference between Heap and Stack?"]
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
                        weightage=f"{percentage:.1f}%",
                        trend=item.get("trend", "Stable"),
                        difficulty=item.get("difficulty", "Moderate"),
                        priority=item.get("priority", 3),
                        keyConcepts=item.get("keyConcepts", []),
                        sampleQuestions=item.get("sampleQuestions", [])
                    )
                )

            final_topics.sort(key=lambda t: t.occurrenceCount, reverse=True)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Enhanced topic analysis complete! Identified {len(final_topics)} topics in {duration:.1f}s.")
            
            return final_topics

        except Exception as e:
            if attempt < settings.GEMINI_MAX_RETRIES - 1:
                wait_time = settings.GEMINI_RETRY_DELAY * (attempt + 1)
                logger.warning(f"Topic analysis attempt {attempt+1} failed: {str(e)[:100]}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Topic analysis failed after {settings.GEMINI_MAX_RETRIES} attempts: {str(e)[:300]}")
                return []
