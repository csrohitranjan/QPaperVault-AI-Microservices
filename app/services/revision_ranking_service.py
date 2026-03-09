import json
import asyncio
from typing import List, Dict
from app.models.schemas import PaperInfo, TopicWeightage
from app.database.mongodb import db, generate_paper_fingerprint
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.paper_processor import process_single_paper
from app.logger import get_logger
import google.generativeai as genai
from app.config import settings

logger = get_logger("revision_ranking_service")

async def _call_gemini_with_retry(model, prompt, max_retries=None):
    """Production-grade Gemini API call with automatic retry."""
    retries = max_retries or settings.GEMINI_MAX_RETRIES
    for attempt in range(retries):
        try:
            response = await model.generate_content_async(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            if attempt < retries - 1:
                wait_time = settings.GEMINI_RETRY_DELAY * (attempt + 1)
                logger.warning(f"Gemini attempt {attempt+1}/{retries} failed: {str(e)[:100]}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Gemini failed after {retries} attempts: {e}")
                return None

async def generate_revision_ranking(paper_code: str, available_hours: int = 4):
    """
    Orchestrates the creation of an advanced urgency-based revision ranking.
    This is a 'One-Stop' revision suite for students.
    """
    logger.info(f"⏳ Generating ADVANCED Last Night Revision Ranking for {paper_code} ({available_hours}h available)")
    
    # 1. Get current papers and fingerprint
    papers = await fetch_papers_by_code(paper_code)
    if not papers:
        return None, None
    fingerprint = generate_paper_fingerprint(papers)
    
    # 2. Extract papers (Layer 1 sync)
    tasks = [process_single_paper(paper) for paper in papers]
    extraction_results = await asyncio.gather(*tasks)
    valid_results = [r for r in extraction_results if r is not None]
    
    if not valid_results:
        return None, None

    # 3. Get Topic Weightage (Feature 2) — AUTO-TRIGGER if missing
    topic_cache = await db.get_cached_result(paper_code, "exam_blueprint_dna", fingerprint)
    if not topic_cache:
        logger.info("📊 Topic DNA not cached. Auto-triggering Topic Analysis...")
        from app.services.topic_analyzer import analyze_topics_from_questions
        topics_result = await analyze_topics_from_questions(valid_results)
        topics_data = [t.model_dump() for t in topics_result]
        await db.save_to_cache(paper_code, "exam_blueprint_dna", fingerprint, {
            "status": 200, "paperName": papers[0].paperName, "paperCode": paper_code,
            "totalPapersAnalyzed": len(valid_results), "topics": topics_data
        })
    else:
        topics_data = topic_cache["result_data"]["topics"]

    # 4. Get Repeated Questions (Feature 1) — AUTO-TRIGGER if missing
    repeated_cache = await db.get_cached_result(paper_code, "smart_pattern_analysis", fingerprint)
    if not repeated_cache:
        logger.info("🔁 Repeated Questions not cached. Auto-triggering Similarity Analysis...")
        from app.services.similarity_analyzer import analyze_similar_questions
        repeated_questions = await analyze_similar_questions(valid_results)
        repeated_data = [q.model_dump() for q in repeated_questions]
        await db.save_to_cache(paper_code, "smart_pattern_analysis", fingerprint, {
            "status": 200, "paperName": papers[0].paperName, "paperCode": paper_code,
            "totalPapersAnalyzed": len(valid_results), "repeatedQuestions": repeated_data
        })
    else:
        repeated_data = repeated_cache["result_data"]["repeatedQuestions"]

    # 5. Get recent question pool (last 2 papers) to check for "Recency"
    recent_pool = []
    for res in valid_results[:2]:
        recent_pool.extend([q["questionText"] for q in res["questions"]])

    # 6. Ask Gemini to curate the ADVANCED ranking
    ranking_data = await curate_advanced_ranking_with_gemini(
        paper_name=papers[0].paperName,
        topics=topics_data,
        repeated_questions=repeated_data,
        recent_pool=recent_pool,
        available_hours=available_hours
    )
    
    return ranking_data, fingerprint

async def curate_advanced_ranking_with_gemini(paper_name: str, topics: List[Dict], repeated_questions: List[Dict], recent_pool: List[str], available_hours: int):
    """Uses Gemini to create a 'One-Stop' revision guide for students."""
    
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    prompt = f"""
    You are an expert exam strategist for "{paper_name}". 
    The student has ONLY {available_hours} hours. This is the LAST NIGHT.
    
    YOUR GOAL: Create a 'One-Stop' revision suite so the student DOES NOT need any other books.
    
    === DATA ===
    - Topic Weightage: {json.dumps(topics, indent=2)}
    - Repeated Questions: {json.dumps(repeated_questions[:15], indent=2)}
    - Asked Recently: {json.dumps(recent_pool[:40], indent=2)}
    
    === YOUR TASK ===
    1. RANK topics by URGENCY (0-100).
    2. For each top topic, provide 'FastAnswers' (concise 2-3 sentence model answers).
    3. Provide 'Mandatory Definitions' and 'Mandatory Diagrams' that guarantee passing marks.
    4. Provide specific 'Skip Advice' (what to ignore to save time).
    5. Allocate exactly {available_hours * 60} minutes across all rankings.
    
    Return ONLY JSON:
    {{
      "urgencyRankings": [
        {{
          "topicName": "...",
          "urgencyScore": 95,
          "estimatedStudyTime": "40 mins",
          "strategy": "Quick Win / Big Fish / Safe Bet",
          "fastAnswers": [
            {{ "question": "...", "answer": "..." }}
          ],
          "criticalConcepts": ["...", "..."],
          "criticalDiagrams": ["...", "..."],
          "skipAdvice": "Ignore X to focus on Y"
        }}
      ],
      "mandatoryDefinitions": ["...", "..."],
      "mandatoryDiagrams": ["...", "..."],
      "passGuaranteeQuestions": ["...", "..."],
      "cheatSheet": "Consolidated formula/definition block"
    }}
    """
    
    return await _call_gemini_with_retry(model, prompt)
