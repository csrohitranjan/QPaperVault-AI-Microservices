import json
import asyncio
from typing import List, Dict
from app.models.schemas import PaperInfo
from app.services.paper_fetcher import fetch_papers_by_code
from app.services.paper_processor import process_single_paper
from app.database.mongodb import db, generate_paper_fingerprint
from app.logger import get_logger
import google.generativeai as genai
from app.config import settings

logger = get_logger("study_notes_generator")

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

async def generate_study_notes(paper_code: str):
    """
    Generates comprehensive, topic-wise study notes by combining:
    1. Topic Weightage (Feature 2) — to know WHAT to focus on
    2. Repeated Questions (Feature 1) — to know WHICH questions matter most
    3. Full Question Pool (Layer 1) — for completeness
    Auto-triggers Features 1 & 2 if they haven't been run.
    """
    logger.info(f"📖 Generating Smart Study Notes for {paper_code}")
    
    # 1. Get current papers and fingerprint
    papers = await fetch_papers_by_code(paper_code)
    if not papers:
        return None, None, 0
    
    fingerprint = generate_paper_fingerprint(papers)
    
    # 2. Get all questions from Paper Library (Layer 1)
    tasks = [process_single_paper(paper) for paper in papers]
    extraction_results = await asyncio.gather(*tasks)
    valid_results = [r for r in extraction_results if r is not None]
    
    if not valid_results:
        return None, None, 0
    
    all_questions_by_year = []
    for i, paper_res in enumerate(extraction_results):
        if paper_res:
            all_questions_by_year.append({
                "year": papers[i].year,
                "month": papers[i].month,
                "questions": [q["questionText"] for q in paper_res["questions"]]
            })
    
    # 3. Get Topic Weightage (Feature 2) — AUTO-TRIGGER if missing
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
        logger.info("✅ Topic DNA auto-generated!")
    else:
        topics_data = topic_cache["result_data"]["topics"]
        logger.info(f"📚 Found {len(topics_data)} topics from Topic Weightage cache")
    
    # 4. Get Repeated Questions (Feature 1) — AUTO-TRIGGER if missing
    repeated_cache = await db.get_cached_result(paper_code, "smart_pattern_analysis", fingerprint)
    if not repeated_cache:
        logger.info("🔁 Repeated Questions not cached. Auto-triggering Similarity Analysis...")
        from app.services.similarity_analyzer import analyze_similar_questions
        repeated_questions = await analyze_similar_questions(valid_results)
        repeated_data = [q.model_dump() for q in repeated_questions]
        # Save to cache
        await db.save_to_cache(paper_code, "smart_pattern_analysis", fingerprint, {
            "status": 200, "paperName": papers[0].paperName, "paperCode": paper_code,
            "totalPapersAnalyzed": len(valid_results), "repeatedQuestions": repeated_data
        })
        logger.info("✅ Repeated Questions auto-generated!")
    else:
        repeated_data = repeated_cache["result_data"]["repeatedQuestions"]
        logger.info(f"🔁 Found {len(repeated_data)} repeated question groups")
    
    # 5. Let Gemini create comprehensive study notes  
    notes_data = await create_notes_with_gemini(
        paper_name=papers[0].paperName,
        topics=topics_data,
        repeated_questions=repeated_data,
        all_questions=all_questions_by_year
    )
    
    return notes_data, fingerprint, len(papers)

async def create_notes_with_gemini(paper_name: str, topics: List[Dict], repeated_questions: List[Dict], all_questions: List[Dict]):
    """Uses Gemini to generate structured, exam-focused study notes."""
    
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    
    # Build repeated questions summary with frequency
    repeated_summary = []
    for rq in repeated_questions[:25]:
        repeated_summary.append({
            "question": rq["question"],
            "frequency": rq["frequency"],
            "appearedIn": rq.get("appearedIn", [])
        })
    
    prompt = f"""
    You are an expert professor creating the ULTIMATE STUDY GUIDE for "{paper_name}".
    Your notes must help a student go from zero preparation to exam-ready.
    
    === DATA FROM PREVIOUS YEAR ANALYSIS ===
    
    TOPIC WEIGHTAGE (Exam importance of each topic):
    {json.dumps(topics, indent=2)}
    
    MOST REPEATED QUESTIONS (These have appeared multiple times — CRITICAL to prepare):
    {json.dumps(repeated_summary, indent=2)}
    
    ALL QUESTIONS FROM PREVIOUS YEARS (Grouped by year):
    {json.dumps(all_questions, indent=2)}
    
    === YOUR TASK ===
    
    Create a professional study guide with this EXACT JSON structure:
    {{
      "studyNotes": [
        {{
          "topicName": "Topic Name",
          "importance": "HIGH",
          "weightage": "25%",
          "difficulty": "Moderate",
          "keyConcepts": [
            {{
              "concept": "Concept Name",
              "explanation": "A clear, detailed 2-3 sentence explanation that a student can use directly in an exam answer. Include formulas or examples where relevant."
            }}
          ],
          "definitions": [
            "Term: A precise, exam-ready definition that can be written directly in an answer sheet."
          ],
          "modelAnswers": [
            {{
              "question": "The exact frequently asked question",
              "answer": "A complete, well-structured model answer (3-5 sentences) that would score full marks in an exam.",
              "frequency": 3
            }}
          ],
          "examTips": [
            "A specific, actionable tip for this topic"
          ],
          "commonMistakes": [
            "A specific mistake students make on this topic"
          ],
          "relatedTopics": ["Other Topic 1", "Other Topic 2"],
          "studyPriority": 1
        }}
      ],
      "predictedQuestions": [
        {{
          "question": "A question likely to appear in the next exam",
          "confidence": "HIGH",
          "reasoning": "Why this is predicted"
        }}
      ],
      "quickRevisionSummary": "A detailed 3-4 paragraph night-before-exam revision guide."
    }}
    
    === QUALITY RULES ===
    1. Order topics by studyPriority (1 = highest, based on weightage + repetition frequency).
    2. HIGH importance = weightage >= 15% OR has 3+ repeated questions.
    3. keyConcepts: Include 4-6 concepts per topic with detailed explanations.
    4. definitions: Include 3-5 per topic (exam-ready, precise, quotable).
    5. modelAnswers: Include 2-4 per topic with COMPLETE answers.
    6. examTips: 2-3 specific, practical tips.
    7. commonMistakes: 2-3 real mistakes students make.
    8. relatedTopics: 1-3 connected topics.
    9. predictedQuestions: Include 5-8 questions with HIGH/MEDIUM confidence.
    10. quickRevisionSummary: Comprehensive last-minute revision guide.
    """
    
    return await _call_gemini_with_retry(model, prompt)
