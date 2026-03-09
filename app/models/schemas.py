from pydantic import BaseModel, Field
from typing import Optional, List

# ──────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────
class RepeatedQuestionsRequest(BaseModel):
    """Request model for repeated questions."""
    paperCode: str = Field(..., description="Subject paper code, e.g. CSIT751")

class TopicAnalysisRequest(BaseModel):
    """Request model for topic weightage analysis."""
    paperCode: str = Field(..., description="Subject paper code, e.g. CSIT751")

class RevisionRankingRequest(BaseModel):
    """Request model for urgency-based revision ranking."""
    paperCode: str = Field(..., description="Subject paper code")
    availableHours: int = Field(4, description="Available study hours")

# ──────────────────────────────────────────────
# Internal Models
# ──────────────────────────────────────────────
class PaperInfo(BaseModel):
    """Represents a single paper fetched from the existing API."""
    id: str
    paperName: str
    paperCode: str
    department: str
    programme: str
    month: str
    year: int
    fileUrl: str

class ExtractedQuestion(BaseModel):
    """A single question extracted from a paper."""
    questionNumber: str
    questionText: str

class PaperWithQuestions(BaseModel):
    """A paper along with its extracted questions."""
    year: int
    month: str
    questions: List[ExtractedQuestion]

# ──────────────────────────────────────────────
# Response Models — Feature 1: Repeated Questions
# ──────────────────────────────────────────────
class QuestionOccurrence(BaseModel):
    """Records when a question appeared."""
    year: int
    month: str

class RepeatedQuestion(BaseModel):
    """A question that appeared in multiple papers."""
    question: str
    frequency: int
    appearedIn: List[QuestionOccurrence]

class RepeatedQuestionsResponse(BaseModel):
    """Response for the repeated question detection endpoint."""
    status: int = 200
    paperCode: str
    paperName: str
    totalPapersAnalyzed: int
    repeatedQuestions: List[RepeatedQuestion]

# ──────────────────────────────────────────────
# Response Models — Feature 2: Topic Weightage
# ──────────────────────────────────────────────
class TopicWeightage(BaseModel):
    """Represents the exam weightage of a single topic."""
    topicName: str
    occurrenceCount: int
    weightage: str  # e.g. "25.5%"

class TopicAnalysisResponse(BaseModel):
    """Response for the topic weightage analysis endpoint."""
    status: int = 200
    paperCode: str
    paperName: str
    totalPapersAnalyzed: int
    topics: List[TopicWeightage]

# ──────────────────────────────────────────────
# Response Models — Feature 3: Mock Test
# ──────────────────────────────────────────────
class MockQuestion(BaseModel):
    """A question included in the curated mock test."""
    questionNumber: int
    questionText: str
    marks: int
    topic: str
    isRepeated: bool = False
    sourceYear: Optional[int] = None
    sourceMonth: Optional[str] = None

class MockTestSection(BaseModel):
    """A section within the mock test (e.g., Section A)."""
    sectionName: str
    sectionDescription: str
    questions: List[MockQuestion]

class MockTestRequest(BaseModel):
    """Request for generating a stratified mock test."""
    paperCode: str = Field(..., description="Subject paper code")
    totalMarks: int = Field(100, description="Target total marks")

class MockTestResponse(BaseModel):
    """Final response containing the full curated mock test."""
    status: int = 200
    paperCode: str
    paperName: str
    totalMarks: int
    examDNAUsed: str # Fingerprint used to craft the test
    testStructure: List[MockTestSection]

# ──────────────────────────────────────────────
# Response Models — Feature 4: Last Night Mode
# ──────────────────────────────────────────────
class FastAnswer(BaseModel):
    """A concise, exam-ready answer for a specific question."""
    question: str
    answer: str

class RankedTopic(BaseModel):
    """An advanced ranked topic with concise study content."""
    topicName: str
    urgencyScore: float
    estimatedStudyTime: str
    strategy: str
    fastAnswers: List[FastAnswer]
    criticalConcepts: List[str]
    criticalDiagrams: List[str]
    skipAdvice: str

class RevisionRankingResponse(BaseModel):
    """Advanced revision guide response."""
    status: int = 200
    paperCode: str
    paperName: str
    urgencyRankings: List[RankedTopic]
    mandatoryDefinitions: List[str]
    mandatoryDiagrams: List[str]
    passGuaranteeQuestions: List[str]
    cheatSheet: str

# ──────────────────────────────────────────────
# Response Models — Feature 5: Smart Study Notes
# ──────────────────────────────────────────────
class ConceptDetail(BaseModel):
    """A key concept with a detailed explanation."""
    concept: str
    explanation: str

class ModelAnswer(BaseModel):
    """A frequently asked question with a model answer."""
    question: str
    answer: str
    frequency: int = 1  # How many times this was asked

class PredictedQuestion(BaseModel):
    """A question predicted to appear in the next exam."""
    question: str
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    reasoning: str

class TopicNote(BaseModel):
    """Comprehensive study note for a single topic."""
    topicName: str
    importance: str  # "HIGH", "MEDIUM", "LOW"
    weightage: str   # e.g. "25%"
    difficulty: str  # "Easy", "Moderate", "Hard"
    keyConcepts: List[ConceptDetail]
    definitions: List[str]
    modelAnswers: List[ModelAnswer]
    examTips: List[str]
    commonMistakes: List[str]
    relatedTopics: List[str]
    studyPriority: int  # 1 = highest priority

class StudyNotesRequest(BaseModel):
    """Request for generating smart study notes."""
    paperCode: str = Field(..., description="Subject paper code")

class StudyNotesResponse(BaseModel):
    """Complete study guide response."""
    status: int = 200
    paperCode: str
    paperName: str
    totalTopics: int
    totalPapersAnalyzed: int
    studyNotes: List[TopicNote]
    predictedQuestions: List[PredictedQuestion]
    quickRevisionSummary: str
