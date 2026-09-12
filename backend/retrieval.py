"""
retrieval.py — Multi-turn RAG query and generation pipeline (v2).

Pipeline (2 LLM calls):
  1. Query Expansion — generate search variations.
  2. Hybrid Search — Vector (ChromaDB) + Keyword (BM25), merged & deduped.
  3. Score-Based Reranking — no LLM call, sort by combined score.
  4. Combined Evidence Check + Generation — single LLM call that both
     evaluates evidence sufficiency AND generates a grounded answer.
"""

import json
import logging
import re
import time
from typing import List, Dict, Any, Tuple, Optional

from google import genai
from rank_bm25 import BM25Okapi

from models import ChatResponse, Citation, ConversationTurn
from ingestion import get_collection, get_genai_client

logger = logging.getLogger(__name__)

GENERATION_MODEL_NAME = "gemini-3.6-flash"
VECTOR_TOP_K = 15
BM25_TOP_K = 10
FINAL_TOP_K = 8
MAX_RETRIES = 3

REFUSAL_PHRASE = "I cannot answer this based on the provided materials."

# In-memory stats counter
_questions_asked = 0
_recent_topics: list = []


def get_stats() -> dict:
    return {
        "total_questions_asked": _questions_asked,
        "recent_topics": _recent_topics[-10:],
    }


# ---------------------------------------------------------------------------
# Gemini call with retry/backoff
# ---------------------------------------------------------------------------
def _call_gemini(prompt: str, max_retries: int = MAX_RETRIES) -> Optional[str]:
    """Call Gemini with automatic retry on 429 rate-limit errors."""
    client = get_genai_client()
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=GENERATION_MODEL_NAME,
                contents=prompt,
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Parse retry delay if available
                wait_time = 15 * (attempt + 1)  # default escalating backoff
                import re as _re
                delay_match = _re.search(r'retryDelay.*?(\d+)s', error_str)
                if delay_match:
                    wait_time = int(delay_match.group(1)) + 1
                if attempt < max_retries:
                    logger.warning(f"Rate limited (attempt {attempt+1}/{max_retries+1}). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            logger.error(f"Gemini call failed: {e}")
            return None
    return None


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------
def _build_history_string(history: List[ConversationTurn]) -> str:
    if not history:
        return ""
    lines = ["=== PRIOR CONVERSATION ==="]
    for turn in history[-6:]:
        role = "Student" if turn.role == "user" else "Assistant"
        lines.append(f"{role}: {turn.content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1: Query Expansion (1 LLM call)
# ---------------------------------------------------------------------------
def _expand_query(question: str, history: List[ConversationTurn]) -> List[str]:
    history_str = _build_history_string(history)
    prompt = (
        "You are an expert search query generator. Given the user's question and conversation history, "
        "generate exactly 3 distinct search queries to maximize retrieval from a study materials knowledge base.\n"
        "- Query 1: The core intent rewritten as a clear, direct search query.\n"
        "- Query 2: Key technical terms and specific keywords extracted from the question.\n"
        "- Query 3: Alternative phrasings using synonyms or related terminology.\n\n"
    )
    if history_str:
        prompt += f"{history_str}\n\n"
    prompt += (
        f"Latest Question: {question}\n\n"
        "Output ONLY a valid JSON array of 3 strings. No markdown fences, no explanation.\n"
        'Example: ["what is classmethod decorator in Python", "classmethod @classmethod decorator", "method bound to class not instance"]'
    )

    text = _call_gemini(prompt)
    if text:
        try:
            # Strip markdown fences if present
            cleaned = text.strip()
            if cleaned.startswith("```"): cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"): cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
            queries = json.loads(cleaned)
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                return queries[:3]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse query expansion JSON: {e}")

    # Fallback: generate queries locally without LLM
    fallback = [question]
    words = question.lower().replace("?", "").replace(".", "").split()
    keywords = [w for w in words if len(w) > 3 and w not in {"what", "does", "that", "this", "from", "with", "about", "have", "been", "they", "their", "which", "would", "could", "should", "explain", "describe"}]
    if keywords:
        fallback.append(" ".join(keywords))
    return fallback


# ---------------------------------------------------------------------------
# Step 2: Hybrid Search (no LLM call)
# ---------------------------------------------------------------------------
def _hybrid_search(queries: List[str]) -> List[Tuple[str, Dict[str, Any], float]]:
    """Perform Vector + BM25 search, return merged candidates with scores."""
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    # --- Vector Search ---
    vector_scores: Dict[str, float] = {}
    vector_data: Dict[str, Tuple[str, Dict[str, Any]]] = {}

    for q in queries:
        try:
            v_res = collection.query(
                query_texts=[q],
                n_results=min(VECTOR_TOP_K, count),
                include=["documents", "metadatas", "distances"]
            )
            docs = v_res.get("documents", [[]])[0]
            metas = v_res.get("metadatas", [[]])[0]
            ids = v_res.get("ids", [[]])[0]
            distances = v_res.get("distances", [[]])[0]
            for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
                # ChromaDB cosine distance: lower = more similar. Convert to similarity.
                similarity = max(0, 1 - dist)
                if doc_id not in vector_scores or similarity > vector_scores[doc_id]:
                    vector_scores[doc_id] = similarity
                    vector_data[doc_id] = (doc, meta)
        except Exception as e:
            logger.error(f"Vector search failed for query '{q}': {e}")

    # --- BM25 Search ---
    bm25_scores: Dict[str, float] = {}
    bm25_data: Dict[str, Tuple[str, Dict[str, Any]]] = {}

    try:
        all_data = collection.get(include=["documents", "metadatas"])
        all_ids = all_data.get("ids", [])
        all_docs = all_data.get("documents", [])
        all_metas = all_data.get("metadatas", [])

        if all_docs:
            tokenized_corpus = [doc.lower().split() for doc in all_docs]
            bm25 = BM25Okapi(tokenized_corpus)

            for q in queries:
                tokenized_query = q.lower().split()
                scores = bm25.get_scores(tokenized_query)
                max_score = max(scores) if max(scores) > 0 else 1
                top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:BM25_TOP_K]
                for idx in top_indices:
                    if scores[idx] > 0:
                        normalized = scores[idx] / max_score  # normalize to 0-1
                        doc_id = all_ids[idx]
                        if doc_id not in bm25_scores or normalized > bm25_scores[doc_id]:
                            bm25_scores[doc_id] = normalized
                            bm25_data[doc_id] = (all_docs[idx], all_metas[idx])
    except Exception as e:
        logger.error(f"BM25 search failed: {e}")

    # --- Merge with combined score ---
    all_candidate_ids = set(vector_scores.keys()) | set(bm25_scores.keys())
    candidates = []
    for doc_id in all_candidate_ids:
        v_score = vector_scores.get(doc_id, 0)
        b_score = bm25_scores.get(doc_id, 0)
        combined = 0.6 * v_score + 0.4 * b_score  # weight semantic higher
        data = vector_data.get(doc_id) or bm25_data.get(doc_id)
        if data:
            candidates.append((data[0], data[1], combined))

    # Sort by combined score descending
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[:FINAL_TOP_K]


# ---------------------------------------------------------------------------
# Step 3: Combined Evidence Check + Answer Generation (1 LLM call)
# ---------------------------------------------------------------------------
def _evaluate_and_generate(
    question: str,
    history: List[ConversationTurn],
    candidates: List[Tuple[str, Dict[str, Any], float]],
) -> Tuple[str, str, List[Citation]]:
    """
    Single LLM call that:
    1. Evaluates evidence sufficiency
    2. If sufficient, generates a grounded answer with inline citations
    Returns (evidence_decision, answer_text, citations)
    """
    history_str = _build_history_string(history)

    # Build context string
    context_lines = []
    for i, (doc, meta, score) in enumerate(candidates):
        fname = meta.get("source_filename", "unknown")
        page = meta.get("page_number", 0)
        context_lines.append(f"[Chunk {i+1} | Source: {fname} | Page: {page}]\n{doc}")
    context_str = "\n\n---\n\n".join(context_lines)

    prompt = (
        "You are a strict academic assistant helping a student study. You must follow these rules exactly:\n\n"
        "STEP 1: Read the CONTEXT CHUNKS below and determine if they contain enough information to answer the QUESTION.\n"
        "STEP 2: Output your evidence assessment as EXACTLY one of: EVIDENCE_DECISION: SUPPORTED, EVIDENCE_DECISION: PARTIALLY_SUPPORTED, or EVIDENCE_DECISION: NOT_SUPPORTED\n"
        "STEP 3:\n"
        "  - If SUPPORTED or PARTIALLY_SUPPORTED: Answer the question using ONLY information from the context chunks. "
        "For every factual claim, include an inline citation in the format [Source_Filename, Page: X]. "
        "Every non-refusal answer must contain at least one such citation. "
        "Do not use any outside knowledge. Be concise and structured.\n"
        "  - If NOT_SUPPORTED: Output EXACTLY: 'I cannot answer this based on the provided materials.'\n\n"
        "CRITICAL RULES:\n"
        "- NEVER make up facts not present in the context chunks.\n"
        "- NEVER cite a page that doesn't actually contain the information.\n"
        "- If only PART of the question can be answered, answer what you can and state what's missing.\n\n"
    )
    if history_str:
        prompt += f"{history_str}\n\n"
    prompt += (
        f"=== CONTEXT CHUNKS ===\n{context_str}\n\n"
        f"=== QUESTION ===\n{question}\n\n"
        "Begin with your EVIDENCE_DECISION line, then your answer (or refusal)."
    )

    text = _call_gemini(prompt)

    if not text:
        return "NOT_SUPPORTED", REFUSAL_PHRASE, []

    # Parse evidence decision
    decision = "NOT_SUPPORTED"
    if "EVIDENCE_DECISION: SUPPORTED" in text:
        decision = "SUPPORTED"
    elif "EVIDENCE_DECISION: PARTIALLY_SUPPORTED" in text:
        decision = "PARTIALLY_SUPPORTED"
    elif "EVIDENCE_DECISION: NOT_SUPPORTED" in text:
        decision = "NOT_SUPPORTED"

    # Extract the answer (everything after the EVIDENCE_DECISION line)
    answer = text
    for prefix in ["EVIDENCE_DECISION: SUPPORTED", "EVIDENCE_DECISION: PARTIALLY_SUPPORTED", "EVIDENCE_DECISION: NOT_SUPPORTED"]:
        if prefix in answer:
            answer = answer.split(prefix, 1)[-1].strip()
            break

    if decision == "NOT_SUPPORTED" or not answer:
        return decision, REFUSAL_PHRASE, []

    # Extract citations from the answer
    citations = []
    matches = re.findall(r'\[([^\[\],]+),\s*Page:\s*(\d+)\]', answer)
    requested_citations = set()
    validated_citations = set()
    for fname, page_str in matches:
        fname = fname.strip()
        try:
            page_num = int(page_str)
            key = (fname, page_num)
            requested_citations.add(key)
            if key not in validated_citations:
                # Find source_type from candidates metadata
                stype = None
                for _, meta, _ in candidates:
                    if meta.get("source_filename") == fname and meta.get("page_number") == page_num:
                        stype = meta.get("source_type")
                        break
                if stype is not None:
                    validated_citations.add(key)
                    citations.append(Citation(filename=fname, page_number=page_num, source_type=stype))
        except ValueError:
            pass

    # A generated answer with missing or invented source/page references is not
    # trustworthy enough for an exam-night study tool. Refuse rather than show
    # an answer that the user cannot verify in the evidence viewer.
    if not citations or requested_citations != validated_citations:
        logger.warning("Answer had absent or unverifiable citations; refusing it.")
        return "NOT_SUPPORTED", REFUSAL_PHRASE, []

    return decision, answer, citations


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def query_and_generate(
    question: str,
    history: List[ConversationTurn] | None = None,
) -> ChatResponse:
    global _questions_asked, _recent_topics

    if history is None:
        history = []

    _questions_asked += 1
    # Extract a short topic label
    topic_words = question.strip()[:60]
    _recent_topics.append(topic_words)
    if len(_recent_topics) > 20:
        _recent_topics = _recent_topics[-20:]

    debug_info: Dict[str, Any] = {"question": question}

    # ── 1. Query Expansion ──
    queries = _expand_query(question, history)
    debug_info["expanded_queries"] = queries
    logger.info(f"[Pipeline] Expanded Queries: {queries}")

    # ── 2. Hybrid Search ──
    candidates = _hybrid_search(queries)
    debug_info["retrieved_candidates_count"] = len(candidates)
    debug_info["retrieved_candidates"] = [
        {"source": c[1].get("source_filename"), "page": c[1].get("page_number"), "score": round(c[2], 3), "preview": c[0][:120]}
        for c in candidates
    ]
    logger.info(f"[Pipeline] Retrieved {len(candidates)} candidates after hybrid search")

    if not candidates:
        debug_info["evidence_decision"] = "NO_CANDIDATES"
        logger.info("[Pipeline] No candidates found → refusing")
        return ChatResponse(answer=REFUSAL_PHRASE, citations=[], debug_info=debug_info)

    # ── 3. Evaluate & Generate (single LLM call) ──
    decision, answer, citations = _evaluate_and_generate(question, history, candidates)
    debug_info["evidence_decision"] = decision
    debug_info["citations_count"] = len(citations)
    logger.info(f"[Pipeline] Evidence Decision: {decision} | Citations: {len(citations)}")

    if answer == REFUSAL_PHRASE:
        citations = []
        # Include searched documents in debug_info for the refusal card
        searched_docs = list(set(c[1].get("source_filename", "unknown") for c in candidates))
        debug_info["searched_documents"] = searched_docs

    return ChatResponse(answer=answer, citations=citations, debug_info=debug_info)
