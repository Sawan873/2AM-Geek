# Evaluation protocol

The challenge requires **20 answerable questions** and **10 questions that are
not covered by the corpus**. This folder keeps the ground truth separate from
the application so a reviewer can audit it.

## Before running

1. Add the permitted, public course corpus to `sample_corpus/`.
2. Upload every file through the app. Confirm that all documents appear in the
   left sidebar.
3. Copy `questions.template.json` to `questions.json` and replace every
   placeholder with a question and the page(s) recorded by hand.

The answerable portion must contain:

- questions `A01`–`A10`: one source document each;
- questions `A11`–`A20`: answers requiring two or more distinct documents;
- questions `R01`–`R10`: syllabus-relevant topics absent from the corpus.

Every answerable question needs every source page that a correct answer must
cite. For a question combining two documents, list both in `required_sources`.

## Run

Start the backend, then from the project root run:

```bash
python test_eval.py --questions evaluation/questions.json
```

The script writes a timestamped JSON report under `evaluation/results/`. It
checks the refusal phrase and the returned citation source/page pairs. It
cannot judge whether a model's wording is academically correct, so review each
answerable result against the recorded sources and fill in
`manual_answer_correct` as `true` or `false` in the report before publishing
your final numbers.

Do not report a score until this review is complete. The evidence report is
intended to accompany the demo or be linked from the README.
