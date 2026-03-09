from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.logger import get_logger
import hashlib
import json
from datetime import datetime, timezone

logger = get_logger("mongodb")

class MongoDB:
    """Production-grade MongoDB helper with Two-Layer Caching."""
    
    # Map DB internal keys to user-facing premium names
    PREMIUM_FEATURE_NAMES = {
        "smart_pattern_analysis": "Smart Pattern Finder",
        "exam_blueprint_dna": "Exam Blueprint DNA",
        "predictive_ai_test": "Predictive AI Mock Test",
        "emergency_pass_strategy": "Emergency Pass Master",
        "ai_masterclass_content": "AI Masterclass Notes"
    }

    def __init__(self):
        self.client = None
        self.db = None
        self.cache_collection = None
        self.ocr_collection = None

    async def connect(self):
        """Connect to MongoDB and ensure indexes."""
        if self.client is None:
            try:
                self.client = AsyncIOMotorClient(settings.MONGODB_URL)
                self.db = self.client[settings.MONGODB_DB_NAME]
                self.cache_collection = self.db["analysis_cache"]
                self.ocr_collection = self.db["paper_ocr_data"]
                
                # Layer 2: Analysis Cache index
                await self.cache_collection.create_index(
                    [("paper_code", 1), ("feature_type", 1), ("fingerprint", 1)],
                    unique=True
                )
                
                # Layer 1: Paper Library (OCR) index
                await self.ocr_collection.create_index("paper_id", unique=True)
                
                logger.info("Connected to MongoDB and verified indexes for both layers.")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")

    async def get_paper_ocr(self, paper_id: str):
        """Retrieve raw OCR questions for a single paper."""
        await self.connect()
        try:
            return await self.ocr_collection.find_one({"paper_id": paper_id})
        except Exception as e:
            logger.error(f"Error fetching paper OCR: {e}")
            return None

    async def save_paper_ocr(self, paper_id: str, questions: list, metadata: dict = None):
        """Save raw OCR questions for a single paper."""
        await self.connect()
        try:
            document = {
                "paper_id": paper_id,
                "questions": questions,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc),
                "last_updated": datetime.now(timezone.utc)
            }
            await self.ocr_collection.replace_one(
                {"paper_id": paper_id},
                document,
                upsert=True
            )
            logger.info(f"Saved Paper Library entry for {paper_id}")
        except Exception as e:
            logger.error(f"Error saving paper OCR: {e}")

    async def get_cached_result(self, paper_code: str, feature_type: str, fingerprint: str):
        """Retrieve a cached result if the fingerprint matches."""
        await self.connect()
        try:
            return await self.cache_collection.find_one({
                "paper_code": paper_code,
                "feature_type": feature_type,
                "fingerprint": fingerprint
            })
        except Exception as e:
            logger.error(f"Error fetching from cache: {e}")
            return None

    async def save_to_cache(self, paper_code: str, feature_type: str, fingerprint: str, result_data: dict, metadata: dict = None):
        """Save analysis result to the cache."""
        await self.connect()
        try:
            document = {
                "paper_code": paper_code,
                "feature_type": feature_type,
                "fingerprint": fingerprint,
                "result_data": result_data,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc),
                "last_updated": datetime.now(timezone.utc)
            }
            await self.cache_collection.replace_one(
                {"paper_code": paper_code, "feature_type": feature_type, "fingerprint": fingerprint},
                document,
                upsert=True
            )
            logger.info(f"Saved cache for {paper_code} ({feature_type}) with fingerprint {fingerprint[:8]}...")
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")

    async def get_library_stats(self):
        """Get statistics for the dashboard/health endpoint."""
        await self.connect()
        try:
            ocr_count = await self.ocr_collection.count_documents({})
            cache_count = await self.cache_collection.count_documents({})
            
            # Get feature-wise breakdown
            pipeline = [
                {"$group": {"_id": "$feature_type", "count": {"$sum": 1}}}
            ]
            feature_stats = {}
            async for doc in self.cache_collection.aggregate(pipeline):
                internal_key = doc["_id"]
                # Map to premium name (handle dynamic keys like emergency_pass_strategy_adv_4h)
                display_name = internal_key
                if internal_key.startswith("emergency_pass_strategy"):
                    display_name = "Emergency Pass Master"
                else:
                    display_name = self.PREMIUM_FEATURE_NAMES.get(internal_key, internal_key)
                
                feature_stats[display_name] = doc["count"]
            
            # Get unique subjects
            subjects = await self.cache_collection.distinct("paper_code")
            
            return {
                "totalPapersInLibrary": ocr_count,
                "totalCachedAnalyses": cache_count,
                "featureBreakdown": feature_stats,
                "subjectsIndexed": subjects,
                "totalSubjects": len(subjects)
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

def generate_paper_fingerprint(papers: list):
    """ Generate a unique fingerprint based on paper IDs. """
    paper_ids = sorted([str(p.id) for p in papers])
    fingerprint_str = ",".join(paper_ids)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()

# Singleton instance
db = MongoDB()
