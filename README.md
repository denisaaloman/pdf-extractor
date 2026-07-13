# PDF Extractor — technical table extractor from PDF

Web app: upload PDF documents (scanned or digital), automatically extract
technical/administrative tables and lists using **Gemini**
(native document understanding on PDF), select what you want, export to
CSV or Excel.

You can open the original document anytime by clicking its name - it opens
directly from the browser's memory, no external storage involved.

## How it works

```
PDF (any type, scanned or digital)
   │
   ▼
Sent WHOLE to Gemini (gemini-3.5-flash) — pages are not rasterized one by
one; Gemini has native document understanding, so it sees the entire
document at once and resolves "Idem"/values continued across pages on its
own, with no manually written merge logic.
   │
   ▼
Output enforced via schema (Pydantic response_schema): each table has
title, category (TEHNIC/ADMINISTRATIV), columns, rows.
The model explicitly excludes the table of contents and descriptive prose,
but does extract numbered lists whose items are self-contained (e.g. an
"Equipment and services list"), even without a visible table border.
"Section header" rows inside a table become an
extra "Sectiune" column propagated down to the rows below them, instead of
being emitted as a separate row.
   │
   ▼
Automatic retry with backoff (2s/4s/8s) if Gemini returns a 503
(model overloaded) - a transient error, not a key/quota issue.
   │
   ▼
Result aggregated across all selected documents
   │
   ▼
Export to CSV / Excel (wide format)
```

### Export format

Each extracted table keeps its own columns (no global union across all
tables in a document — that would generate an excessive amount of empty
cells).

- **Excel**: one **sheet per document**. Each sheet is in wide format:
  `Tabel | Categorie | Rand | <all unique columns found in that
  document's tables>`. A row only has values in the columns of the table
  it came from, the rest stay empty — you can immediately see which
  table/section a value belongs to, and it's easy to filter/pivot.
- **CSV**: a single file (CSV doesn't support multiple sheets), with an
  extra `Fisier` column to distinguish documents.

## Project structure

```
main.py           — FastAPI: /api/extract, /api/export, serves the static frontend
extraction.py     — Gemini client (google-genai), Pydantic schema, prompt, retry
export_utils.py   — builds the wide format and generates CSV/XLSX
static/
  index.html      — main UI
  styles.css      — styles
  app.js          — frontend logic (vanilla JS, no framework)
requirements.txt
.env
```

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# edit .env and add your Gemini key (from https://aistudio.google.com/apikey):
# GEMINI_API_KEY=...

uvicorn main:app --reload
```

Open http://localhost:8000

> On Windows, if you edit `.env`, restart the server — it's loaded once
> at startup, not live.