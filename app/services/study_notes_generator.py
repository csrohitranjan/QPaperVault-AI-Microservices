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

async def generate_study_notes(paper_code: str, token: str = None):
    """
    Generates comprehensive, topic-wise study notes by combining:
    1. Topic Weightage (Feature 2) — to know WHAT to focus on
    2. Repeated Questions (Feature 1) — to know WHICH questions matter most
    3. Full Question Pool (Layer 1) — for completeness
    Auto-triggers Features 1 & 2 if they haven't been run.
    """
    logger.info(f"📖 Generating Smart Study Notes for {paper_code}")
    
    # 1. Get current papers and fingerprint
    papers = await fetch_papers_by_code(paper_code, token)
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
    You are an expert professor and subject matter expert creating the ABSOLUTE DEFINITIVE MASTERCLASS STUDY GUIDE for "{paper_name}".
    
    === MISSION CRITICAL ===
    Your goal is COMPLETE COVERAGE. Every single question found in the "RAW QUESTION POOL" must be accounted for. 
    If a concept has been asked ONCE in the last 10 years, it MUST have a dedicated section in these notes. 
    A student reading this should not need any other textbook to pass with a top grade.

    === DATA SOURCE: PREVIOUS YEAR PAPERS ===
    
    TOPIC WEIGHTAGE (Fundamental Importance):
    {json.dumps(topics, indent=2)}
    
    MOST REPEATED QUESTIONS (High-frequency patterns):
    {json.dumps(repeated_summary, indent=2)}
    
    RAW QUESTION POOL (The source of truth - extract EVERY topic from here):
    {json.dumps(all_questions, indent=2)}
    
    === YOUR TASK ===
    1. Scan every question in the RAW QUESTION POOL.
    2. Group them into granular, logical topics.
    3. For EACH topic, generate deep, exhaustive masterclass content.
    
    You MUST use this EXACT JSON structure. DO NOT CHANGE ANY KEYS.
    {{
      "studyNotes": [
        {{
          "topicName": "Granular Topic Title",
          "importance": "HIGH/MEDIUM/LOW",
          "weightage": "X%",
          "difficulty": "Easy/Moderate/Hard",
          "keyConcepts": [
            {{
              "concept": "Specific Detail/Sub-concept",
              "explanation": "A high-density academic explanation (4-6 sentences). Must be a complete 'ready-to-memorize' node for the student."
            }}
          ],
          "definitions": [
            "Term: A rigorous, formal definition that captures 100% of the marks."
          ],
          "modelAnswers": [
            {{
              "question": "Standard Exam Question Pattern",
              "answer": "An exhaustive 'Model Answer' (5-8 sentences) formatted with logical points and deep technical insight.",
              "frequency": 3
            }}
          ],
          "examTips": [
            "Expert advice on keywords and diagrams required for this topic."
          ],
          "commonMistakes": [
            "Conceptual errors that lead to marks being deducted."
          ],
          "relatedTopics": ["Related Topic A", "Related Topic B"],
          "studyPriority": 1
        }}
      ],
      "predictedQuestions": [
        {{
          "question": "Highly probable future exam question",
          "confidence": "HIGH",
          "reasoning": "Data-driven justification"
        }}
      ],
      "quickRevisionSummary": "A massive, high-impact 5-8 paragraph 'Expert Revision' guide that synthesizes the entire subject into a rapid-read format."
    }}
    
    === MASTERCLASS QUALITY RULES ===
    1. EXHAUSTIVE TOPICS: Provide 12-25 granular topics/sub-topics. Do not skip any area mentioned in the questions.
    2. 100% COVERAGE: Map every unique question from the raw question pool to a Masterclass Node.
    3. ACADEMIC RIGOR: Use professional, technical language. No shallow summaries.
    4. VOLUME: Each topic MUST have 6-10 'keyConcepts' and 5-8 'definitions'.
    5. MODEL ANSWERS: Provide 4-6 deep model answers per topic, especially for the high-frequency/repeated questions.
    6. PREDICTED QUESTIONS: Generate a robust list of 15-20 questions that haven't appeared recently but follow the exam DNA.
    7. RANKING: studyPriority 1 = Top Priority (Weightage + Repetition).
    """
    
    return await _call_gemini_with_retry(model, prompt)
