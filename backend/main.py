"""
main.py — FastAPI application entry point.

Endpoints:
  POST   /api/upload               — Ingest a file (PDF/image/text)
  GET    /api/documents            — List all ingested documents
  DELETE /api/documents/{filename} — Remove a document from ChromaDB
  POST   /api/chat                 — Ask a question (RAG + guardrail)
"""

import os
import shutil
import logging
from pathlib import Path

import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from models import ChatRequest, ChatResponse, UploadResponse, DocumentsResponse, DocumentInfo, QuizRequest, QuizResponse, QuizQuestion, QuizOption, Citation, StatsResponse, CorpusReadinessResponse
from ingestion import ingest_pdf, ingest_image, ingest_text, delete_document, list_documents, get_document_chunks, get_collection, get_corpus_readiness
from retrieval import query_and_generate, get_stats, _call_gemini, invalidate_retrieval_cache

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY or GEMINI_API_KEY == "your_api_key_here":
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Please add your key to the .env file in the project root."
    )

# Ensure the key is in the environment for google-genai SDK
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_DB_DIR = Path(__file__).parent / "chroma_db"
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

STORED_IMAGES_DIR = Path(__file__).parent / "stored_images"
STORED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Multimodal RAG Study Tool", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Allowed file types
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".md": "text",
    ".txt": "text",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Accept a file, save it temporarily, run the ingestion pipeline, then delete the temp file."""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {list(ALLOWED_EXTENSIONS.keys())}",
        )

    file_type = ALLOWED_EXTENSIONS[suffix]
    tmp_path = UPLOAD_DIR / filename

    # Save upload to disk
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Run ingestion
    try:
        logger.info(f"Starting ingestion for: {filename} (type={file_type})")
        if file_type == "pdf":
            chunks_stored = ingest_pdf(str(tmp_path), filename)
        elif file_type == "image":
            chunks_stored = ingest_image(str(tmp_path), filename)
        else:
            chunks_stored = ingest_text(str(tmp_path), filename)
    except Exception as e:
        logger.error(f"Ingestion failed for {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")
    finally:
        # Always clean up the temp file
        if tmp_path.exists():
            tmp_path.unlink()

    invalidate_retrieval_cache()
    return UploadResponse(filename=filename, chunks_stored=chunks_stored)


@app.get("/api/documents", response_model=DocumentsResponse)
async def get_documents():
    """Return a list of all unique documents currently stored in ChromaDB."""
    try:
        docs = list_documents()
        return DocumentsResponse(
            documents=[DocumentInfo(filename=d["filename"], chunks=d["chunks"]) for d in docs]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{filename}")
async def remove_document(filename: str):
    """Remove all chunks for the given filename from ChromaDB."""
    try:
        deleted = delete_document(filename)
        invalidate_retrieval_cache()
        return {"filename": filename, "chunks_deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """RAG chat endpoint with hallucination guardrail and multi-turn memory."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        response = query_and_generate(request.question, history=request.history or [])
        return response
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", response_model=StatsResponse)
async def stats():
    """Return dashboard statistics."""
    try:
        from ingestion import get_collection as _gc
        collection = _gc()
        total_chunks = collection.count()
        docs = list_documents()
        total_documents = len(docs)
        rag_stats = get_stats()
        return StatsResponse(
            total_documents=total_documents,
            total_chunks=total_chunks,
            total_questions_asked=rag_stats["total_questions_asked"],
            recent_topics=rag_stats["recent_topics"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/readiness", response_model=CorpusReadinessResponse)
async def corpus_readiness():
    """Expose submission-requirement progress without fabricating manual checks."""
    try:
        return CorpusReadinessResponse(**get_corpus_readiness())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/images/{filename:path}")
async def serve_image(filename: str):
    """Serve a stored image for the evidence viewer."""
    file_path = STORED_IMAGES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path))


@app.post("/api/quiz", response_model=QuizResponse)
async def generate_quiz(request: QuizRequest):
    """Generate MCQ questions strictly from a specific document's content."""
    chunks = get_document_chunks(request.filename)
    if not chunks:
        raise HTTPException(status_code=404, detail=f"No chunks found for '{request.filename}'.")

    # Build context from the document's chunks
    context_parts = []
    for chunk in chunks[:30]:  # Limit to avoid exceeding context window
        page = chunk.get("page_number", "?")
        context_parts.append(f"[Page {page}]\n{chunk['text']}")
    context_str = "\n\n---\n\n".join(context_parts)

    prompt = (
        f"You are a strict exam question generator. Based ONLY on the following course material from '{request.filename}', "
        f"generate exactly {request.num_questions} multiple choice questions.\n\n"
        "RULES:\n"
        "- Each question must be answerable from the provided material.\n"
        "- Each question must have exactly 4 options labeled A, B, C, D.\n"
        "- Include the correct answer label and a brief explanation.\n"
        "- Include the page number where the answer can be found.\n"
        "- Do NOT use any knowledge outside the provided material.\n\n"
        f"=== COURSE MATERIAL ===\n{context_str}\n\n"
        "Output ONLY a valid JSON array. Each element must have this exact structure:\n"
        '[{"question": "...", "options": [{"label": "A", "text": "..."}, {"label": "B", "text": "..."}, {"label": "C", "text": "..."}, {"label": "D", "text": "..."}], "correct_answer": "A", "explanation": "...", "page_number": 1}]\n'
        "No markdown fences. No commentary. Just the JSON array."
    )

    text = _call_gemini(prompt)
    if not text:
        raise HTTPException(status_code=500, detail="Failed to generate quiz questions. Try again.")

    try:
        # Clean markdown fences
        cleaned = text.strip()
        if cleaned.startswith("```"): cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"): cleaned = cleaned.rsplit("```", 1)[0]
        raw_questions = json.loads(cleaned.strip())
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse quiz response. Try again.")

    questions = []
    for rq in raw_questions[:request.num_questions]:
        options = [QuizOption(label=o["label"], text=o["text"]) for o in rq.get("options", [])]
        citation = Citation(
            filename=request.filename,
            page_number=rq.get("page_number", 1),
            source_type="pdf"
        )
        questions.append(QuizQuestion(
            question=rq["question"],
            options=options,
            correct_answer=rq.get("correct_answer", "A"),
            explanation=rq.get("explanation", ""),
            citation=citation,
        ))

    return QuizResponse(filename=request.filename, questions=questions)
