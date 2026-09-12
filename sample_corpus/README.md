# Sample Corpus Instructions

This folder is where you put your real course materials before running the evaluation.

## What you need (minimum requirements from the problem statement)

| # | Type | Requirement |
|---|------|-------------|
| 1 | PDF | Lecture notes (multiple pages) |
| 2 | PDF | Another set of lecture notes or slides |
| 3 | PDF | A document with **diagrams, tables, or equations** |
| 4 | TXT or MD | A markdown/text notes file |
| 5 | JPG/PNG | A **clear** photo of handwritten notes |
| 6 | JPG/PNG | A **genuinely hard to read** scan (bad lighting, angle, etc.) |
| 7+ | Any | More documents to reach 60+ total pages |

**Total:** At least 60 pages across at least 4 different formats.

## Naming convention

Use descriptive names so citations are meaningful in the UI:
- `Lecture_01_Intro.pdf`
- `Week3_Slides.pdf`
- `Algorithms_Cheat_Sheet.md`
- `Handwritten_Notes_Lab2.jpg`
- `Scanned_Notes_Hard.png`  ← the deliberately difficult one

## How to ingest

Once the backend is running, either:
1. **Drag and drop** files using the UI at http://localhost:5173
2. **Use curl** (faster for bulk uploads):

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@Lecture_01_Intro.pdf"
```

## eval_questions.json format

After ingesting, create your 30 test questions in `eval_questions.json`:

```json
[
  {
    "id": 1,
    "question": "Your question here",
    "expected_type": "answer",
    "correct_source": "Lecture_01_Intro.pdf",
    "correct_page": 4,
    "notes": "Single-document question"
  },
  {
    "id": 21,
    "question": "An out-of-scope question",
    "expected_type": "refusal",
    "correct_source": null,
    "correct_page": null,
    "notes": "Not in any uploaded document"
  }
]
```

Run the full evaluation:
```bash
python test_eval.py --questions eval_questions.json
```
