#!/usr/bin/env python3
"""Run the challenge evaluation against a running 2AM Geek backend.

The evaluator checks two things automatically:
  * each answerable question has all hand-recorded source/page citations; and
  * each out-of-scope question returns the exact refusal and no citations.

It deliberately leaves semantic answer correctness for a human reviewer. The
saved JSON report has a ``manual_answer_correct`` field for that review.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REFUSAL_PHRASE = "I cannot answer this based on the provided materials."
DEFAULT_HOST = "http://localhost:8000"
DEFAULT_QUESTIONS = "evaluation/questions.json"
RESULTS_DIR = Path("evaluation/results")


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def server_is_ready(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/health", timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def citation_pairs(citations: list[dict]) -> set[tuple[str, int]]:
    pairs = set()
    for citation in citations:
        try:
            pairs.add((citation["filename"], int(citation["page_number"])))
        except (KeyError, TypeError, ValueError):
            continue
    return pairs


def validate_questions(questions: object) -> list[str]:
    errors = []
    if not isinstance(questions, list):
        return ["The question file must contain a JSON array."]

    answer_count = 0
    refusal_count = 0
    seen_ids = set()
    for index, item in enumerate(questions, start=1):
        label = f"entry {index}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object.")
            continue
        question_id = item.get("id")
        question = item.get("question", "")
        expected_type = item.get("expected_type")
        sources = item.get("required_sources")
        if not question_id or question_id in seen_ids:
            errors.append(f"{label} needs a unique id.")
        seen_ids.add(question_id)
        if not isinstance(question, str) or not question.strip() or "REPLACE" in question:
            errors.append(f"{label} needs a real question, not a placeholder.")
        if expected_type not in {"answer", "refusal"}:
            errors.append(f"{label} must set expected_type to answer or refusal.")
            continue
        if not isinstance(sources, list):
            errors.append(f"{label} required_sources must be an array.")
            continue
        if expected_type == "answer":
            answer_count += 1
            if not sources:
                errors.append(f"{label} is answerable but has no recorded source page.")
            for source in sources:
                if not isinstance(source, dict) or not source.get("filename") or not isinstance(source.get("page_number"), int):
                    errors.append(f"{label} has an invalid required_sources entry.")
                elif "REPLACE" in source["filename"]:
                    errors.append(f"{label} still contains a placeholder filename.")
        else:
            refusal_count += 1
            if sources:
                errors.append(f"{label} is a refusal test and must not list source pages.")

    if answer_count != 20:
        errors.append(f"Expected exactly 20 answerable questions; found {answer_count}.")
    if refusal_count != 10:
        errors.append(f"Expected exactly 10 refusal questions; found {refusal_count}.")
    return errors


def percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate citations and refusals for The Night Before.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Backend base URL")
    parser.add_argument("--questions", default=DEFAULT_QUESTIONS, help="Hand-labeled question JSON")
    parser.add_argument("--delay", default=0.4, type=float, help="Seconds between requests")
    parser.add_argument("--results-dir", default=str(RESULTS_DIR), help="Directory for the JSON report")
    args = parser.parse_args()

    questions_path = Path(args.questions)
    try:
        questions = json.loads(questions_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Question file not found: {questions_path}")
        print("Copy evaluation/questions.template.json to evaluation/questions.json, then label it by hand.")
        return 2
    except json.JSONDecodeError as error:
        print(f"Invalid JSON in {questions_path}: {error}")
        return 2

    validation_errors = validate_questions(questions)
    if validation_errors:
        print("Question set is not ready:")
        for error in validation_errors:
            print(f"  - {error}")
        return 2

    if not server_is_ready(args.host):
        print(f"Backend is not reachable at {args.host}. Start it before evaluating.")
        return 2

    results = []
    print("\nRunning 30 hand-labeled challenge questions…\n")
    for item in questions:
        started = time.monotonic()
        expected_type = item["expected_type"]
        expected_pairs = citation_pairs(item["required_sources"])
        result = {
            "id": item["id"],
            "question": item["question"],
            "expected_type": expected_type,
            "required_sources": item["required_sources"],
            "manual_answer_correct": None,
        }
        try:
            response = post_json(f"{args.host}/api/chat", {"question": item["question"], "history": []})
            answer = response.get("answer", "")
            citations = response.get("citations", [])
            returned_pairs = citation_pairs(citations)
            is_refusal = answer.strip() == REFUSAL_PHRASE
            citations_match = expected_pairs.issubset(returned_pairs)
            if expected_type == "answer":
                automatic_pass = not is_refusal and citations_match
            else:
                automatic_pass = is_refusal and not citations
            result.update(
                answer=answer,
                citations=citations,
                citation_match=citations_match if expected_type == "answer" else None,
                refusal_returned=is_refusal,
                automatic_pass=automatic_pass,
                elapsed_seconds=round(time.monotonic() - started, 2),
            )
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
            result.update(error=str(error), automatic_pass=False)
        except Exception as error:  # Keep the report useful if one request is malformed.
            result.update(error=f"Unexpected error: {error}", automatic_pass=False)

        results.append(result)
        marker = "PASS" if result["automatic_pass"] else "FAIL"
        detail = "citation match" if expected_type == "answer" else "refusal"
        print(f"{marker:4}  {item['id']:>3}  {expected_type:7}  {detail}")
        time.sleep(max(args.delay, 0))

    answer_results = [item for item in results if item["expected_type"] == "answer"]
    refusal_results = [item for item in results if item["expected_type"] == "refusal"]
    answer_passes = sum(item["automatic_pass"] for item in answer_results)
    refusal_passes = sum(item["automatic_pass"] for item in refusal_results)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "question_file": str(questions_path),
        "automatic_summary": {
            "answerable_questions_with_all_required_citations": f"{answer_passes}/{len(answer_results)}",
            "answerable_citation_rate_percent": percent(answer_passes, len(answer_results)),
            "correct_refusals": f"{refusal_passes}/{len(refusal_results)}",
            "refusal_rate_percent": percent(refusal_passes, len(refusal_results)),
        },
        "manual_review_required": "Review each answer against its recorded pages and set manual_answer_correct before reporting final accuracy.",
        "results": results,
    }

    output_dir = Path(args.results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"evaluation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nAutomatic results")
    print(f"  Answerable questions with all required citations: {answer_passes}/{len(answer_results)}")
    print(f"  Correct refusals: {refusal_passes}/{len(refusal_results)}")
    print(f"  Report: {output_path}")
    print("  Next: review each answer for correctness before publishing any final score.")
    return 0 if answer_passes == len(answer_results) and refusal_passes == len(refusal_results) else 1


if __name__ == "__main__":
    sys.exit(main())
