import json
import asyncio
from typing import List, Dict
from app.models.schemas import MockTestSection, MockQuestion, PaperInfo, TopicWeightage
from app.database.mongodb import db, generate_paper_fingerprint
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.paper_processor import process_single_paper
from app.logger import get_logger
import google.generativeai as genai
from app.config import settings

logger = get_logger("mock_generator")

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

async def generate_stratified_mock_test(paper_code: str, total_marks: int = 100, token: str = None):
    """
    Orchestrates the creation of a mock test based on 'Exam DNA'.
    Auto-triggers Feature #2 (Topic Weightage) if not cached.
    """
    logger.info(f"🎨 Generating Mock Test for {paper_code} ({total_marks} marks)")
    
    # 1. Get current papers and fingerprint
    papers = await fetch_papers_by_code(paper_code, token)
    if not papers:
        return None
    fingerprint = generate_paper_fingerprint(papers)
    
    # Process papers to get valid_results for subsequent steps
    tasks = [process_single_paper(paper) for paper in papers]
    extraction_results = await asyncio.gather(*tasks)
    valid_results = [r for r in extraction_results if r is not None]
    
    if not valid_results:
        logger.error(f"No valid questions extracted for paper code {paper_code}.")
        return None

    # 2. Get Topic Weightage (Feature 2) — AUTO-TRIGGER if missing
    topic_cache = await db.get_cached_result(paper_code, "exam_blueprint_dna", fingerprint)
    if not topic_cache:
        logger.info("📊 Topic DNA not cached. Auto-triggering Topic Analysis...")
        from app.services.topic_analyzer import analyze_topics_from_questions
        topics_result = await analyze_topics_from_questions(valid_results)
        topics_data = [t.model_dump() for t in topics_result]
        # Save to cache
        await db.save_to_cache(paper_code, "exam_blueprint_dna", fingerprint, {
            "status": 200, "paperName": papers[0].paperName, "paperCode": paper_code,
            "totalPapersAnalyzed": len(valid_results), "topics": topics_data
        })
    else:
        topics_data = topic_cache["result_data"]["topics"]
    
    # 3. Get Repeated Questions (Priority items) — AUTO-TRIGGER if missing
    repeated_cache = await db.get_cached_result(paper_code, "smart_pattern_analysis", fingerprint)
    repeated_texts = []
    if repeated_cache:
        repeated_texts = [q["question"] for q in repeated_cache["result_data"]["repeatedQuestions"]]
    else:
        logger.info("🔁 Repeated Questions not cached. Auto-triggering Similarity Analysis...")
        from app.services.similarity_analyzer import analyze_similar_questions
        repeated_questions = await analyze_similar_questions(valid_results)
        repeated_data = {
            "status": 200, "paperCode": paper_code, "paperName": papers[0].paperName,
            "totalPapersAnalyzed": len(valid_results), "repeatedQuestions": [q.model_dump() for q in repeated_questions]
        }
        await db.save_to_cache(paper_code, "smart_pattern_analysis", fingerprint, repeated_data, {"paper_ids": [p.id for p in papers]})
        repeated_texts = [q.question for q in repeated_questions]
        logger.info("✅ Repeated Questions auto-generated!")

    # 4. Get all questions pool
    all_questions = []
    for paper_res in extraction_results:
        if paper_res:
            all_questions.extend(paper_res["questions"])

    # 5. Ask Gemini to curate the paper
    mock_test = await curate_with_gemini(
        paper_name=papers[0].paperName,
        topics=topics_data,
        repeated_questions=repeated_texts,
        all_pool=all_questions,
        total_marks=total_marks
    )
    
    return mock_test, fingerprint

async def curate_with_gemini(paper_name: str, topics: List[Dict], repeated_questions: List[str], all_pool: List[Dict], total_marks: int):
    """Uses Gemini to select and format the mock test following the DNA blueprint."""
    
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    prompt = f"""
    You are an expert exam paper setter for {paper_name}.
    You need to create a MOCK TEST of {total_marks} marks.
    
    THE DNA (Topic Distribution to follow):
    {json.dumps(topics, indent=2)}
    
    HIGH PRIORITY QUESTIONS (These are repeated questions - include them if they fit):
    {json.dumps(repeated_questions[:20], indent=2)}
    
    FULL POOL OF AVAILABLE QUESTIONS:
    {json.dumps([q['questionText'] for q in all_pool[:100]], indent=2)}
    
    INSTRUCTIONS:
    1. Select questions that match the Topic Weightage distribution.
    2. Divide the paper into three sections:
       - Section A: Short Questions (2 marks each)
       - Section B: Medium Questions (5 marks each)
       - Section C: Long Questions (10 marks each)
    3. Ensure the total marks are exactly {total_marks}.
    4. Provide the result in a valid JSON format only, with this structure:
    {{
      "testStructure": [
        {{
          "sectionName": "Section A",
          "sectionDescription": "Short Answer Questions",
          "questions": [
            {{
              "questionNumber": 1,
              "questionText": "...",
              "marks": 2,
              "topic": "Topic Name",
              "isRepeated": true
            }}
          ]
        }}
      ]
    }}
    """
    
    return await _call_gemini_with_retry(model, prompt)
