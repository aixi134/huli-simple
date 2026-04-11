# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

### Backend setup
- Create venv and install deps:
  - `SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m venv .venv`
  - `SSL_CERT_FILE=/etc/ssl/cert.pem .venv/bin/pip install -r backend/requirements.txt`
- Start API:
  - `PYTHONPATH=. .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`
- Syntax check backend/scripts:
  - `python3 -m compileall backend scripts`

### Frontend setup
- Install deps:
  - `npm install --prefix frontend`
- Start dev server:
  - `npm run dev --prefix frontend`
- Production build:
  - `npm run build --prefix frontend`

### Parser and import workflow
- Parse a single PDF to JSON:
  - `.venv/bin/python scripts/parse_pdf_to_json.py "pdf/...sample.pdf"`
- Parse without LLM fallback:
  - `.venv/bin/python scripts/parse_pdf_to_json.py "pdf/...sample.pdf" --no-fallback`
- Batch parse corpus:
  - `.venv/bin/python scripts/batch_extract.py --source-dir pdf`
  - limit the batch during debugging with `--limit N`
- Import one parsed JSON file into SQLite:
  - `.venv/bin/python scripts/import_questions.py "data/parsed_questions/<file>.json"`
- Import a directory of parsed JSON files:
  - `.venv/bin/python scripts/import_questions.py --dir data/parsed_questions`

### Quick API checks
- Health:
  - `python3 - <<'PY'`
    `import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())`
    `PY`
- Random question:
  - `python3 - <<'PY'`
    `import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/question/random').read().decode())`
    `PY`

## Environment notes

- Python package installation may fail on this machine unless `SSL_CERT_FILE=/etc/ssl/cert.pem` is set.
- The local OpenAI-compatible multimodal model is expected at `http://127.0.0.1:8888/v1`.
- LLM features require `QUIZ_LLM_API_KEY` or `OPENAI_API_KEY`; without one, parser fallback and AI explanation endpoints will raise a clear runtime error.
- The current default local model name is `Qwen3.5-27B-Claude-4.6-Opus-Distilled-MLX-4bit` and can be overridden with `QUIZ_LLM_MODEL`.

## Architecture

- `pdf/` is the read-only source corpus. It is mixed-format: mostly PDF, plus some `.doc`/`.docx`. MVP scripts only process PDFs and explicitly skip Word files in batch mode.
- The project is split into three runtime areas:
  - `backend/` — FastAPI app, SQLAlchemy models, parser services, and local LLM integration
  - `scripts/` — command-line entrypoints for PDF parsing, batch extraction, and JSON-to-SQLite import
  - `frontend/` — Vite + React single-page quiz UI
- Generated artifacts live under `data/`:
  - `data/raw_pages/` — per-PDF extracted page text JSON
  - `data/parsed_questions/` — structured question-bank JSON
  - `data/failed/` — rendered pages and failed/fallback artifacts
  - `data/quiz.db` — SQLite database

## Backend structure

- `backend/app/main.py` defines the FastAPI app and the three main API endpoints:
  - `GET /health`
  - `GET /question/random`
  - `POST /answer`
  - `POST /question/{id}/ai-explanation`
- `backend/app/db.py` initializes SQLite and session management.
- `backend/app/models.py` stores normalized question data across `questions` and `options`, with uniqueness on `(source_file, question_number)` to prevent duplicate imports.
- `backend/app/crud.py` contains random-question lookup, question serialization, and JSON import logic.
- `backend/app/schemas.py` holds FastAPI request/response models.

## Parser architecture

- Rule-based parsing lives in `backend/app/services/parser_rules.py`.
- The parser supports two main source patterns already seen in the corpus:
  - inline-answer PDFs such as `5、2025【高频考题】-主管护师/*.pdf` where each question contains `答案：X`
  - exam + answer-section PDFs such as `主管护师历年真题/2023真题试卷/*.pdf` where questions appear first and `参考答案及解析` appears later
- The parser also handles B1 shared-option sections by extracting option groups from blocks like `【90-91】` and reusing them for subsequent numbered questions.
- `scripts/parse_pdf_to_json.py` is the main single-file pipeline:
  1. extract page text with PyMuPDF
  2. save raw page JSON
  3. isolate question section / answer section
  4. split numbered questions
  5. parse stem/options/answers
  6. merge into structured JSON
- If a PDF has no extractable text, the script treats it as scanned and falls back to page-image rendering plus multimodal extraction via the local LLM.
- `scripts/batch_extract.py` scans the whole corpus, processes PDFs, and records success/failed/skipped summaries. It deliberately skips `.doc`/`.docx` in the MVP.

## Frontend structure

- `frontend/src/App.jsx` owns the quiz flow: load random question, select answer, submit, show result, fetch next question, request AI explanation.
- `frontend/src/api.js` wraps fetch calls to the backend.
- `frontend/src/components/QuestionCard.jsx` renders the prompt/options.
- `frontend/src/components/AnswerResult.jsx` renders correctness, explanation, and AI explanation.
- The frontend assumes the backend is running on `http://127.0.0.1:8000` unless overridden with `VITE_API_BASE_URL`.

## Known repository-specific constraints

- Some PDFs are text-based and parse well with rules; others are scanned/image-heavy and need the local multimodal model.
- The local multimodal endpoint currently responds to `/health` and requires an API key for `/v1/chat/completions`.
- A verified text-based sample for parser regression testing is:
  - `pdf/主管护师历年真题/2023真题试卷/2023年主管护师基础知识试卷【雪狐狸】..pdf`
- A scanned sample that currently depends on multimodal OCR fallback is:
  - `pdf/3、2025【历年真题】-主管护师/2022年真题试卷/2022年主管护师基础知识试卷.pdf`
