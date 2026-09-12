"""Fast, grounded multi-turn RAG retrieval and answer generation.

Each uncached question makes one model request: the combined evidence decision
and answer-generation request. Query variants and BM25 indexing are local, so
they add negligible latency while preserving the citation guardrail.
"""

import hashlib
import json
import logging
import re
import time
from typing import List, Dict, Any, Tuple, Optional

from google import genai
from google.genai import types as genai_types
from rank_bm25 import BM25Okapi

from models import ChatResponse, Citation, ConversationTurn
from ingestion import get_collection, get_genai_client

logger = logging.getLogger(__name__)

GENERATION_MODEL_NAME = "gemini-2.0-flash"
VECTOR_TOP_K = 15
BM25_TOP_K = 10
FINAL_TOP_K = 6
MAX_RETRIES = 1
GENERATION_TIMEOUT_MS = 15_000
MAX_ANSWER_TOKENS = 450
ANSWER_CACHE_MAX_ENTRIES = 50

REFUSAL_PHRASE = "I cannot answer this based on the provided materials."

# In-memory stats counter
_questions_asked = 0
_recent_topics: list = []
_answer_cache: Dict[str, ChatResponse] = {}
_bm25_index: Optional[Tuple[BM25Okapi, List[str], List[str], List[Dict[str, Any]]]] = None


def get_stats() -> dict:
    return {
        "total_questions_asked": _questions_asked,
        "recent_topics": _recent_topics[-10:],
    }


def invalidate_retrieval_cache() -> None:
    """Clear per-corpus caches after any upload or document deletion."""
    global _bm25_index
    _answer_cache.clear()
    _bm25_index = None
    logger.info("Retrieval caches invalidated after corpus change.")


# ---------------------------------------------------------------------------
# Gemini call with retry/backoff
# ---------------------------------------------------------------------------
def _call_gemini(prompt: str, max_retries: int = MAX_RETRIES) -> Optional[str]:
    """Call Gemini with a short interactive timeout and one quick retry."""
    client = get_genai_client()
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=GENERATION_MODEL_NAME,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=MAX_ANSWER_TOKENS,
                    http_options=genai_types.HttpOptions(timeout=GENERATION_TIMEOUT_MS),
                ),
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries:
                    logger.warning("Rate limited; retrying once in 2 seconds.")
                    time.sleep(2)
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
# Step 1: Fast local query variants (no LLM call)
# ---------------------------------------------------------------------------
_QUERY_STOP_WORDS = {
    "about", "been", "could", "describe", "does", "explain", "from", "have",
    "that", "their", "this", "they", "what", "which", "with", "would",
    "your", "please", "according", "notes", "material", "materials",
}


def _keywords(text: str, limit: int = 12) -> List[str]:
    words = re.findall(r"[A-Za-z0-9_@+-]{3,}", text.lower())
    return [word for word in words if word not in _QUERY_STOP_WORDS][:limit]


def _build_search_queries(question: str, history: List[ConversationTurn]) -> List[str]:
    """Create recall-friendly variants locally, avoiding a second API round trip."""
    queries = [question.strip()]
    current_keywords = _keywords(question)
    if current_keywords:
        queries.append(" ".join(current_keywords))

    # Add the previous student topic only for follow-up questions. This keeps
    # conversational context without asking a model to rewrite the query.
    prior_user_turns = [turn.content for turn in history if turn.role == "user"]
    if prior_user_turns and current_keywords:
        prior_keywords = _keywords(prior_user_turns[-1], limit=6)
        if prior_keywords:
            queries.append(" ".join(current_keywords + prior_keywords))

    return list(dict.fromkeys(query for query in queries if query))


# ---------------------------------------------------------------------------
# Step 2: Hybrid Search (no LLM call)
# ---------------------------------------------------------------------------
def _get_bm25_index(collection) -> Tuple[Optional[BM25Okapi], List[str], List[str], List[Dict[str, Any]]]:
    """Build BM25 once per corpus rather than once per student question."""
    global _bm25_index
    if _bm25_index is not None:
        return _bm25_index

    all_data = collection.get(include=["documents", "metadatas"])
    all_ids = all_data.get("ids", [])
    all_docs = all_data.get("documents", [])
    all_metas = all_data.get("metadatas", [])
    if not all_docs:
        return None, [], [], []
    bm25 = BM25Okapi([doc.lower().split() for doc in all_docs])
    _bm25_index = (bm25, all_ids, all_docs, all_metas)
    return _bm25_index


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
        bm25, all_ids, all_docs, all_metas = _get_bm25_index(collection)

        if bm25 is not None:
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


def _answer_cache_key(question: str, history: List[ConversationTurn]) -> str:
    payload = {
        "question": question.strip(),
        "history": [(turn.role, turn.content) for turn in history[-6:]],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_response(cache_key: str, response: ChatResponse) -> None:
    if len(_answer_cache) >= ANSWER_CACHE_MAX_ENTRIES:
        _answer_cache.pop(next(iter(_answer_cache)))
    _answer_cache[cache_key] = response


def _extractive_evidence_fallback(
    candidates: List[Tuple[str, Dict[str, Any], float]],
) -> Tuple[str, List[Citation]]:
    """Return short, verbatim evidence when the model misses its response budget.

    This is intentionally not presented as an AI-generated explanation. It lets
    a student inspect the best matching material immediately without making up
    an answer while a provider is slow or rate limited.
    """
    passages = []
    citations = []
    seen = set()
    for document, metadata, _ in candidates:
        filename = metadata.get("source_filename", "unknown")
        page_number = metadata.get("page_number", 0)
        source_type = metadata.get("source_type")
        key = (filename, page_number)
        if key in seen or not source_type:
            continue
        seen.add(key)
        excerpt = re.sub(r"\s+", " ", document).strip()[:600]
        if not excerpt:
            continue
        passages.append(f"> {excerpt}\n\n[{filename}, Page: {page_number}]")
        citations.append(Citation(filename=filename, page_number=page_number, source_type=source_type))
        if len(passages) == 2:
            break

    answer = (
        "**Quick evidence view**\n\n"
        "The cited-answer service did not respond within the 15-second study-time budget, "
        "so I will not invent a summary. These are the most relevant passages to verify:\n\n"
        + "\n\n".join(passages)
    )
    return answer, citations


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
        fallback_answer, fallback_citations = _extractive_evidence_fallback(candidates)
        if fallback_citations:
            return "EXTRACTIVE_FALLBACK", fallback_answer, fallback_citations
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

    started_at = time.perf_counter()
    cache_key = _answer_cache_key(question, history)
    cached_response = _answer_cache.get(cache_key)
    if cached_response is not None:
        cached_debug = dict(cached_response.debug_info or {})
        cached_debug.update({
            "question": question,
            "cache_hit": True,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        })
        return ChatResponse(
            answer=cached_response.answer,
            citations=cached_response.citations,
            debug_info=cached_debug,
        )

    debug_info: Dict[str, Any] = {
        "question": question,
        "cache_hit": False,
        "retrieval_strategy": "local query variants + vector/BM25 hybrid search",
    }

    # ── 1. Local query variants ──
    queries = _build_search_queries(question, history)
    debug_info["expanded_queries"] = queries
    logger.info(f"[Pipeline] Local search queries: {queries}")

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
        debug_info["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
        logger.info("[Pipeline] No candidates found → refusing")
        response = ChatResponse(answer=REFUSAL_PHRASE, citations=[], debug_info=debug_info)
        _cache_response(cache_key, response)
        return response

    # ── 3. Evaluate & Generate (single LLM call) ──
    decision, answer, citations = _evaluate_and_generate(question, history, candidates)
    debug_info["evidence_decision"] = decision
    debug_info["citations_count"] = len(citations)
    debug_info["fallback_used"] = decision == "EXTRACTIVE_FALLBACK"
    logger.info(f"[Pipeline] Evidence Decision: {decision} | Citations: {len(citations)}")

    if answer == REFUSAL_PHRASE:
        citations = []
        # Include searched documents in debug_info for the refusal card
        searched_docs = list(set(c[1].get("source_filename", "unknown") for c in candidates))
        debug_info["searched_documents"] = searched_docs

    debug_info["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
    response = ChatResponse(answer=answer, citations=citations, debug_info=debug_info)
    _cache_response(cache_key, response)
    return response
