# ISL Interpreter — General Workplace

Two-way Indian Sign Language interpreter for public-facing workplaces
(offices, hospitals, banks, counters). Runs fully offline; SQLite is the
only datastore.

- **Pipeline A (hearing → Deaf):** speech/text → ISL gloss → avatar playback.
- **Pipeline B (Deaf → hearing):** camera-based sign recognition → text/speech.

See `backend/README.md` for the backend's implementation status in detail.

## Layout

- `backend/` — FastAPI + SQLite. See below.
- `frontend/` — not built yet.

## Quick start (backend)

```
cd backend
cp .env.example .env      # fill in GROQ_API_KEY only if you want the online fallback
pip install -r requirements.txt
python -m app.database.local_db   # creates data/isl.db
python -m scripts.seed_vocabulary
python run.py
```

Then check `http://127.0.0.1:8000/docs`.
