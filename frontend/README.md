# Frontend

Not built yet. Backend endpoints are documented in `backend/README.md`
and live at `http://127.0.0.1:8000/docs` once `backend/run.py` is running.

Two screens are expected, matching the two pipelines:
- Speak/Type screen (Pipeline A): posts to `/translate/forward`, plays
  the returned avatar sequences.
- Sign/Camera screen (Pipeline B): streams MediaPipe landmarks to
  `/recognize/ws`, shows the recognized sentence for confirmation before
  speaking it.
