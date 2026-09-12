# 2AM Geek — The Night Before

> You have fourteen hours until the exam. Ask your actual course material, get
> an evidence-grounded answer, and open the exact page to verify it.

**Submission problem:** 4 · **The Night Before**

2AM Geek is a multi-turn study companion for lecture PDFs, slides, text notes,
and photographs of handwriting. It is deliberately not a generic summariser:
every answer is generated only from retrieved course material, and the app
refuses questions that the material does not support.

## What makes it a study tool

- **Source-level trust.** Answers include source and page citations. Clicking a
  citation opens the original rendered PDF page or the uploaded note image.
- **Handwriting is first-class.** Photos and scans are processed with vision
  OCR, retained as original images, and clearly labelled for user verification.
  This matters most for imperfect scans: the app shows what was actually
  uploaded instead of pretending the extraction is clean.
- **It remembers the study session.** The last six turns are included in
  retrieval and generation, so follow-up questions such as “compare that with
  the previous algorithm” have context.
- **Grounded refusal.** The evidence gate can return `NOT_SUPPORTED`; then the
  only answer is: `I cannot answer this based on the provided materials.` The
  UI shows which documents were searched.
- **Exam mode.** Generate cited multiple-choice questions from a selected
  source without bringing in outside knowledge.
- **Judge mode.** Press `Ctrl+Shift+D` to inspect query expansion, retrieved
  chunks, scores, and the evidence decision.

## How it works

1. Files are ingested page by page. PDFs are rendered and sent to vision OCR;
   text and Markdown files are split while keeping synthetic page positions.
2. Each chunk is stored with its filename, page number, source type, and—when
   applicable—the path to its original image.
3. A question is expanded into retrieval queries and searched with vector
   similarity plus BM25 keyword search.
4. The top evidence chunks are passed to one strict prompt. It first decides
   whether there is enough evidence, then either generates cited claims or
   refuses. Returned citations are accepted only when they match retrieved
   filename/page metadata.

The normal question path uses **one Gemini request**, not one request to
rewrite the search query followed by another to answer it. Search variants and
the BM25 index are built locally; exact repeated questions in the same corpus
are served from a small in-memory cache. Uploading or deleting a document
invalidates that cache, so an answer never outlives the corpus it was based on.

For an interactive study session, generation has a 15-second response budget
and one short rate-limit retry. If the provider cannot return a grounded answer
in time, 2AM Geek immediately shows labelled **verbatim evidence excerpts**
with citations. It never disguises those excerpts as a generated answer.

## Run locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Gemini API key
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/) on
  your `PATH` for rendered PDF-page evidence. Text-layer PDFs can fall back to
  `pdfplumber` if Poppler is unavailable.

### Start the app

```bash
git clone <your-public-repository-url>
cd 2AM-Geek
copy .env.example .env
# Add your GEMINI_API_KEY to .env

cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Upload the corpus from
the left panel, then ask a question.

> macOS/Linux users can use `cp .env.example .env` instead of `copy`.

## What is mocked?

**Nothing in the RAG path is mocked.** OCR, query expansion, evidence
assessment, answer generation, and quiz generation use the configured Gemini
API. If there is no API key, the backend fails at startup rather than silently
using invented content.

The repository intentionally contains **no course corpus or reported score
yet**. Course files may have privacy, permission, or publisher restrictions;
only material that may be made public should be added. The `sample_corpus/`
folder and `evaluation/questions.template.json` are instructions/templates,
not evidence that the challenge requirements have been met.

## Challenge corpus and evaluation

Before submission, add a permitted public corpus with:

- at least 60 pages across PDFs/slides, Markdown or text, and two photographed
  handwritten pages;
- at least four source formats;
- a diagram, table, or equation; and
- one genuinely difficult handwritten scan (bad light, angle, or low clarity).

Then create 20 hand-labelled answerable questions: 10 single-document and 10
requiring multiple documents. Add 10 syllabus-relevant questions absent from
the corpus. Record every correct source/page by hand in the evaluation file.

```bash
copy evaluation\questions.template.json evaluation\questions.json
# Edit questions.json with the real corpus filenames, questions, and pages.
python test_eval.py --questions evaluation/questions.json
```

The evaluator verifies all expected citation pairs and all refusals, then
writes a reviewable JSON report in `evaluation/results/`. A person must still
mark whether each answer is academically correct before publishing the final
score. Full instructions: [evaluation/README.md](evaluation/README.md).

## Demo checklist

Record a short, uncut video that shows:

1. the application running locally;
2. uploading a photographed handwritten note;
3. a question answered from that note, followed by opening its citation;
4. a multi-document question; and
5. an out-of-scope syllabus question being refused.

Include the final evaluation numbers in this README only after the hand review
is complete.

## Project structure

```text
backend/                 FastAPI, ingestion, hybrid retrieval, and guardrails
frontend/                React/Vite interface and evidence viewer
sample_corpus/           Instructions for adding a permitted public corpus
evaluation/              Ground-truth template and evaluation protocol
test_eval.py             Citation/refusal evaluator that emits JSON evidence
```

## License

MIT
