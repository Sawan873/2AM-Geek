from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ── Chat schemas ──────────────────────────────────────────────────────────────

class ConversationTurn(BaseModel):
    role: str          # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: List[ConversationTurn] = Field(default_factory=list)  # prior turns for multi-turn memory


class Citation(BaseModel):
    filename: str
    page_number: int
    source_type: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    debug_info: Optional[Dict[str, Any]] = None


# ── Upload / document schemas ─────────────────────────────────────────────────

class UploadResponse(BaseModel):
    filename: str
    chunks_stored: int


class DocumentInfo(BaseModel):
    filename: str
    chunks: int


class DocumentsResponse(BaseModel):
    documents: List[DocumentInfo]

# ── Quiz schemas ──────────────────────────────────────────────────────────────

class QuizRequest(BaseModel):
    filename: str
    num_questions: int = 5

class QuizOption(BaseModel):
    label: str  # A, B, C, D
    text: str

class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption]
    correct_answer: str  # The label (A, B, C, D)
    explanation: str
    citation: Citation

class QuizResponse(BaseModel):
    filename: str
    questions: List[QuizQuestion]

# ── Stats schemas ─────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_questions_asked: int
    recent_topics: List[str]


class CorpusReadinessResponse(BaseModel):
    total_documents: int
    ingested_pages: int
    formats: List[str]
    image_sources: int
    checks: List[Dict[str, Any]]
