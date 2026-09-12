"""
ingestion.py — Multimodal ingestion pipeline.

Handles:
  - PDFs: each page converted to an image → sent to Gemini Vision for text extraction
  - Images (JPEG/PNG): sent directly to Gemini Vision
  - Text/Markdown: read directly, split by paragraphs
"""

import os
import io
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any

from google import genai
from google.genai import types as genai_types
from PIL import Image
import pdfplumber
from pdf2image import convert_from_path
import chromadb

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini Vision model for OCR
# ---------------------------------------------------------------------------
VISION_MODEL_NAME = "gemini-3.6-flash"
CHUNK_SIZE = 800          # characters per chunk
CHUNK_OVERLAP = 120       # character overlap between chunks

# ---------------------------------------------------------------------------
# ChromaDB client (module-level singleton so it's shared)
# ---------------------------------------------------------------------------
CHROMA_DB_PATH = Path(__file__).parent / "chroma_db"
STORED_IMAGES_DIR = Path(__file__).parent / "stored_images"
STORED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
COLLECTION_NAME = "study_materials"

_chroma_client = None
_collection = None
_genai_client = None


def get_genai_client():
    global _genai_client
    if _genai_client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client


def get_collection() -> chromadb.Collection:
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# ---------------------------------------------------------------------------
# Gemini Vision helper
# ---------------------------------------------------------------------------
def _extract_text_from_pil_image(pil_image: Image.Image) -> str:
    """Send a PIL image to Gemini Vision and return extracted text."""
    client = get_genai_client()
    prompt = (
        "You are an expert OCR assistant. Extract ALL text from this image exactly as it appears. "
        "Include handwritten text, printed text, equations, tables, and any other textual content. "
        "Preserve the original structure as much as possible. Output ONLY the extracted text, "
        "with no commentary or explanation."
    )
    response = client.models.generate_content(
        model=VISION_MODEL_NAME,
        contents=[prompt, pil_image],
    )
    return response.text.strip() if response.text else ""


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------
def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping character-level chunks."""
    chunks: List[str] = []
    text = text.strip()
    if not text:
        return chunks
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
def _store_chunks(
    chunks: List[str],
    filename: str,
    page_numbers: List[int],
    collection: chromadb.Collection,
    source_type: str,
    image_path: str = None,
) -> int:
    """Store a list of text chunks in ChromaDB with strict metadata."""
    if not chunks:
        return 0

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for chunk, page_num in zip(chunks, page_numbers):
        chunk_id = str(uuid.uuid4())
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append(
            {
                "source_filename": filename,
                "page_number": page_num,
                "source_type": source_type,
                "chunk_id": chunk_id,
                **(({"image_path": image_path} if image_path else {}))
            }
        )

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


# ---------------------------------------------------------------------------
# Ingestors
# ---------------------------------------------------------------------------
def ingest_pdf(file_path: str, filename: str) -> int:
    """
    Ingest a PDF file.
    Each page is rendered to an image and sent to Gemini Vision for OCR.
    Returns the total number of chunks stored.
    """
    collection = get_collection()
    total_chunks = 0

    try:
        pages: List[Image.Image] = convert_from_path(file_path, dpi=200)
    except Exception as e:
        logger.error(f"pdf2image failed for {filename}: {e}. Falling back to pdfplumber text extraction.")
        pages = []

    if pages:
        for page_number, page_image in enumerate(pages, start=1):
            logger.info(f"Processing PDF page {page_number}/{len(pages)} of {filename} via Gemini Vision…")
            try:
                extracted_text = _extract_text_from_pil_image(page_image)
            except Exception as e:
                logger.error(f"Gemini Vision failed on page {page_number}: {e}")
                extracted_text = ""

            if not extracted_text:
                continue

            page_image.save(str(STORED_IMAGES_DIR / f"{filename}_page_{page_number}.png"), "PNG")
            chunks = _chunk_text(extracted_text)
            page_numbers = [page_number] * len(chunks)
            stored = _store_chunks(chunks, filename, page_numbers, collection, source_type="pdf", image_path=str(STORED_IMAGES_DIR / f"{filename}_page_{page_number}.png"))
            total_chunks += stored
    else:
        # Fallback: use pdfplumber for text-layer PDFs
        with pdfplumber.open(file_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if not text.strip():
                    continue
                chunks = _chunk_text(text)
                page_numbers_list = [page_number] * len(chunks)
                stored = _store_chunks(chunks, filename, page_numbers_list, collection, source_type="pdf")
                total_chunks += stored

    return total_chunks


def ingest_image(file_path: str, filename: str) -> int:
    """
    Ingest a single image (JPEG/PNG).
    Sends the image to Gemini Vision and stores as one or more chunks.
    Returns the total number of chunks stored.
    """
    collection = get_collection()

    pil_img = Image.open(file_path)
    # Ensure RGB mode for compatibility
    if pil_img.mode not in ("RGB", "L"):
        pil_img = pil_img.convert("RGB")
        
    import shutil
    stored_path = STORED_IMAGES_DIR / filename
    shutil.copy2(file_path, str(stored_path))

    logger.info(f"Processing image {filename} via Gemini Vision…")
    extracted_text = _extract_text_from_pil_image(pil_img)

    if not extracted_text:
        return 0

    chunks = _chunk_text(extracted_text)
    page_numbers = [1] * len(chunks)
    return _store_chunks(chunks, filename, page_numbers, collection, source_type="image", image_path=str(stored_path))


def ingest_text(file_path: str, filename: str) -> int:
    """
    Ingest a plain text or Markdown file.
    Splits by paragraphs, assigns synthetic page numbers (every ~40 lines ≈ 1 page).
    Returns the total number of chunks stored.
    """
    collection = get_collection()
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Split on blank lines (paragraph-style)
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    lines_per_page = 40

    all_chunks: List[str] = []
    all_pages: List[int] = []
    cumulative_lines = 0

    for para in paragraphs:
        para_lines = para.count("\n") + 1
        page_number = (cumulative_lines // lines_per_page) + 1
        chunks = _chunk_text(para)
        all_chunks.extend(chunks)
        all_pages.extend([page_number] * len(chunks))
        cumulative_lines += para_lines

    return _store_chunks(all_chunks, filename, all_pages, collection, source_type="text")


# ---------------------------------------------------------------------------
# Delete helpers
# ---------------------------------------------------------------------------
def delete_document(filename: str) -> int:
    """Remove all chunks for a given source_filename from ChromaDB."""
    collection = get_collection()
    results = collection.get(where={"source_filename": filename})
    ids = results.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def list_documents() -> List[Dict[str, Any]]:
    """Return a list of unique documents with their chunk counts."""
    collection = get_collection()
    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", [])

    counts: Dict[str, int] = {}
    for meta in metadatas:
        fname = meta.get("source_filename", "unknown")
        counts[fname] = counts.get(fname, 0) + 1

    return [{"filename": fname, "chunks": count} for fname, count in counts.items()]


def get_corpus_readiness() -> Dict[str, Any]:
    """Summarise objective corpus requirements without claiming manual evidence.

    Page counts are conservative: a page counts only when at least one chunk was
    successfully ingested. Handwriting quality and permission cannot be proven
    automatically, so they remain explicitly manual checks in the response.
    """
    collection = get_collection()
    results = collection.get(include=["metadatas"])
    documents: Dict[str, Dict[str, Any]] = {}
    for metadata in results.get("metadatas", []):
        filename = metadata.get("source_filename", "unknown")
        entry = documents.setdefault(
            filename,
            {
                "pages": set(),
                "extension": Path(filename).suffix.lower() or "unknown",
                "source_type": metadata.get("source_type", "unknown"),
            },
        )
        entry["pages"].add(metadata.get("page_number", 0))

    total_pages = sum(len(entry["pages"]) for entry in documents.values())
    formats = sorted({entry["extension"] for entry in documents.values()})
    image_sources = sum(1 for entry in documents.values() if entry["source_type"] == "image")
    checks = [
        {
            "label": "60+ successfully ingested source pages",
            "passed": total_pages >= 60,
            "detail": f"{total_pages}/60 pages",
        },
        {
            "label": "Four or more uploaded file formats",
            "passed": len(formats) >= 4,
            "detail": f"{len(formats)}/4 formats ({', '.join(formats) or 'none'})",
        },
        {
            "label": "Two photographed handwritten-note sources",
            "passed": image_sources >= 2,
            "detail": f"{image_sources}/2 image sources — manually confirm they are permitted handwriting photos.",
        },
        {
            "label": "Diagram, table, or equation source included",
            "passed": False,
            "detail": "Manual review required; visual content cannot be verified from chunk metadata.",
        },
        {
            "label": "Difficult handwritten scan included",
            "passed": False,
            "detail": "Manual review required; keep one genuinely hard-to-read photo in the public corpus.",
        },
        {
            "label": "30 hand-labelled evaluation questions",
            "passed": False,
            "detail": "Manual review required; add evaluation/questions.json and record source pages by hand.",
        },
    ]
    return {
        "total_documents": len(documents),
        "ingested_pages": total_pages,
        "formats": formats,
        "image_sources": image_sources,
        "checks": checks,
    }

def get_document_chunks(filename: str) -> List[Dict[str, Any]]:
    """Return all chunks and metadata for a specific document."""
    collection = get_collection()
    results = collection.get(
        where={"source_filename": filename},
        include=["documents", "metadatas"]
    )
    chunks = []
    for doc, meta in zip(results.get("documents", []), results.get("metadatas", [])):
        chunks.append({"text": doc, **meta})
    return chunks
