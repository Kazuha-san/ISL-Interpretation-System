# ISL Interpreter — Backend

## Status: v0.5.0 — both pipelines scaffolded, Pipeline B waiting on a trained model

Fully offline-capable. `GROQ_API_KEY` is optional everywhere — leave it
blank in `.env` and the app runs entirely on the local rule-based gloss
engine. SQLite (`data/isl.db`, WAL mode) is the only datastore; there is
no cloud dependency anywhere in this codebase.

## Pipeline A — hearing → Deaf (`/translate`)

Working end to end for the 44-word pilot vocabulary:

1. `POST /translate/forward` — transcript → gloss → avatar sequences.
   Resolution order: approved cache → local rule engine (if confidence ≥0.85)
   → Groq (only if `GROQ_API_KEY` set, 3s timeout) → local best-effort →
   full fingerspell fallback. See `app/services/gloss.py`.
2. `app/services/local_gloss.py` — deterministic ISL grammar rules
   (topic-comment order, WH-word/negation moved to the end, articles and
   copulas dropped), reading vocabulary from SQLite. No LLM required.
3. `app/services/retrieval.py` — resolves gloss tokens to avatar keypoint
   sequences. Currently returns `None` for every word (no `sign_clips`
   rows exist yet — nothing has been seeded beyond the vocabulary table
   itself). `MOCK_KEYPOINTS=true` only affects words that *do* have a
   clip row; it does not fabricate clips that don't exist.
4. `GET /vocabulary`, `GET /vocabulary/{id}` — lexicon lookup, includes
   `has_clip` so the frontend can tell which words are actually playable.

**Blocked on:** real keypoint JSON per word. Once the ISLRTC-sourced
extraction pipeline (discussed separately) produces `assets/clips/keypoints/{word}.json`
files and `sign_clips` rows pointing at them, set `MOCK_KEYPOINTS=false`
and Pipeline A is feature-complete for whatever vocabulary has been
processed.

## Pipeline B — Deaf → hearing (`/recognize`)

Scaffolded, not functional yet — there is no trained recognition model
to load, and nothing here fakes one.

1. `app/routers/recognize.py` — WebSocket endpoint (`/recognize/ws`).
   Only landmark frames travel over the wire, never video — the camera
   and MediaPipe extraction are assumed to run client-side. Full wire
   protocol is documented in the file's docstring.
2. `app/services/recognition.py` — buffers incoming landmark frames per
   connection. `SignRecognizer._run_inference()` raises `NotImplementedError`
   deliberately — this is the exact spot to wire in a trained model once
   one exists. Every other piece (buffering, the WebSocket protocol,
   session logging, sentence assembly) is already built against the
   return shape that method needs to produce.
3. `app/services/gloss_to_text.py` — two-layer sentence assembly, mirroring
   Pipeline A's approach: `assemble_sentence()` is rule-based (inverse of
   `local_gloss.py`'s ordering) and always available offline;
   `assemble_sentence_smart()` additionally asks Groq to naturalize that
   draft when `GROQ_API_KEY` is set, falling back to the draft on any
   failure or timeout. Every recognized sentence is still shown to the
   signer for confirmation (`recognition_sessions.confirmed`) before it's
   spoken — smoothing reduces how much editing that needs, it doesn't
   remove the need for it.
4. `recognition_sessions` table (`app/database/local_db.py`) — stores
   every recognition attempt plus the signer's confirm/correct action.
   This is also where training/eval data for a future model accumulates.

**Blocked on:** a trained isolated/continuous sign recognition model.
Set `RECOGNIZER_MODEL_PATH` in `.env` and implement `_load_model()` /
`_run_inference()` in `recognition.py` once one exists.

## Other endpoints

- `/session` — explicit session lifecycle (used by Pipeline B; Pipeline A
  creates its own sessions inline per-request).
- `/qna` — approved Q&A packs for a kiosk.
- `/admin/cache` — approve/reject Groq-sourced cache entries before they're
  trusted for future local hits.

## Known placeholders (kept intentionally, not stubs left by accident)

- `app/services/asr.py`, `app/services/tts.py` — empty on purpose. Speech
  recognition and synthesis both run client-side via the browser's Web
  Speech API; these exist only in case a future kiosk needs server-side
  versions.
- `app/models/staff.py` / `StaffProgressResponse` — model exists,
  no router uses it yet (no staff-facing practice UI built yet).
- `app/utils/helpers.py` — empty; nothing has needed a shared helper yet.

## Setup

```
cp .env.example .env
pip install -r requirements.txt
python -m app.database.local_db     # creates data/isl.db with the current schema
python -m scripts.seed_vocabulary   # loads assets/vocabulary/vocab.csv (44 words)
python -m scripts.seed_quick_phrases  # optional: pre-computed staff quick-phrases
python run.py
```

## Security note

The `.env` that shipped in earlier working copies of this repo contained
a live `GROQ_API_KEY` and Supabase credentials. Supabase is fully removed
from the code (this app has never needed it since — SQLite only), but
**rotate the Groq key** regardless — it was already outside version
control's protection once, in a shared file. Deleting it from the repo
doesn't undo that exposure.
