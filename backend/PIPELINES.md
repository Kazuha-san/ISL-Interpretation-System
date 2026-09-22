# Pipelines — Technical Overview

Both pipelines share one SQLite database (`backend/data/isl.db`) and one
lexicon (the `vocabulary` table), so a word added for one pipeline is
immediately available to the other. This document explains how each
pipeline actually works end to end, and exactly where each one currently
stops due to missing data (not missing code).

---

## Shared foundation

- **`vocabulary` table** — every known word: English label, Hindi label,
  a `gloss_tag` (the canonical ISL sign identifier, e.g. `NAME`, `WHAT`),
  and a category. This table is the single source of truth both
  pipelines read from.
- **`sign_clips` table** — links a vocabulary entry to its avatar
  keypoint data (`keypoint_json_path`). Currently empty — this is what
  Pipeline A's playback is waiting on.
- **Keypoint schema** — whether generated for the avatar or consumed by
  the recognizer, landmark frames follow one shape:
  ```json
  {
    "pose": [[x, y, z], ...33 points],
    "left_hand": [[x, y, z], ...21 points],
    "right_hand": [[x, y, z], ...21 points],
    "face_blendshapes": {"browDownLeft": 0.02, "jawOpen": 0.15, ...}
  }
  ```
  Using the same shape on both sides means the same MediaPipe extraction
  work fed Pipeline A's avatar clips can also become Pipeline B's
  training data later.

---

## Pipeline A — hearing → Deaf

**Goal:** turn spoken or typed Hindi/English into a sequence of avatar
signs.

### Step by step

1. **Input.** The frontend captures speech via the browser's Web Speech
   API, or the user types directly. Either way, the backend only ever
   receives text — `POST /translate/forward` with `{transcript, context,
   language}`. `context` (general, banking, health, identity, education)
   only affects which sign wins when a sentence is ambiguous between two
   valid vocabulary options; it never restricts which words can be used.

2. **Resolution order** (`app/services/gloss.py`,
   `convert_to_gloss_smart()`), tried in this order until one succeeds:
   1. **Cache hit.** `resolved_phrases_cache` — an exact match on the
      normalized input + context, but only entries marked `approved`
      (see step 5) are trusted.
   2. **Local rule engine, high confidence (≥0.85).** Used directly, no
      network call at all.
   3. **Groq fallback**, only if `GROQ_API_KEY` is set — 3 second
      timeout, so a slow/unreachable network never stalls the kiosk.
   4. **Local rule engine, best-effort.** If Groq was unreachable or
      unset and local confidence was at least 0.5.
   5. **Full fingerspell fallback.** If local confidence was below 0.5
      and Groq was unavailable — every word gets spelled out letter by
      letter rather than the system giving no output at all.

3. **Local rule engine** (`app/services/local_gloss.py`) — fully
   deterministic, offline, reads vocabulary from SQLite (never
   hardcoded):
   - Strips filler words (articles, auxiliary verbs, possessives —
     English list is solid; the Hindi filler list is a first draft
     flagged as needing native-speaker review).
   - Matches remaining words against `vocabulary` by English or Hindi
     label.
   - Applies ISL grammar ordering: **WH-words** (WHAT/WHERE/WHEN/WHO/
     HOW_MUCH/WHICH) move to the end of the sequence; **negation** (NO)
     moves to the end, before the WH-word if both are present.
   - Returns a confidence score = matched words ÷ total content words.

4. **Token resolution → avatar sequences**
   (`app/services/retrieval.py`) — for each gloss token, look up its
   `sign_clips` row and read the keypoint JSON it points to. **This is
   currently the dead end**: no `sign_clips` rows exist yet, so every
   lookup returns `None` and the word is reported in the response's
   `fallbacks` list. `MOCK_KEYPOINTS=true` only produces a placeholder
   for words that *do* have a `sign_clips` row — it does not fabricate
   entries that don't exist, so this mode has had nothing to affect
   since the table has been empty.
   - **Fingerspelling** (`app/services/fingerspell.py`) is the fallback
     path when a word truly has no vocabulary match — it looks up a
     per-letter clip reference from `assets/fingerspell/{LETTER}.mp4`.

5. **Caching and review.** Every Groq result is cached as
   `pending_review`, never auto-trusted. `/admin/cache` exposes
   `GET /pending`, `POST /cache/{id}/approve`, `POST /cache/{id}/reject`
   — a human reviews Groq's gloss output once, and after approval it
   becomes a free, instant, offline cache hit for every future occurrence
   of that exact phrase.

6. **Session logging.** Every `/translate/forward` call creates a
   `sessions` row (`direction='A'`) and a matching `session_logs` row
   (input text, gloss output, whether a fallback was used). This is
   analytics/audit trail, not used to shape behavior.

7. **Quick phrases.** `GET /translate/quick-phrases?context=...` and
   `POST /translate/quick-phrase/{id}` serve pre-computed gloss for
   common staff phrases ("What is your name?", "Please wait") —
   computed once via `scripts/seed_quick_phrases.py`, so selecting one
   at runtime is instant with zero gloss-engine work.

### What Pipeline A needs to be complete

Real keypoint JSON per vocabulary word, plus a `sign_clips` row pointing
at it. The planned source is the ISLRTC public ISL dictionary
(~10,000 terms, licensed for non-commercial research and ISL technology
development, attribution required) run through the same MediaPipe
extraction the team already built, plus the team's own recordings for
whatever ISLRTC doesn't cover. Nothing else in Pipeline A is blocked.

---

## Pipeline B — Deaf → hearing

**Goal:** watch a Deaf person sign through the camera, recognize what
they signed, and speak it back once they confirm it's correct.

### Why confirmation before speaking

Recognizing continuous sign language is hard, and reversing ISL grammar
back into English is lossy no matter how it's done. Rather than trusting
either step blindly, every recognized sentence is shown to the signer
before it's spoken aloud. This isn't a workaround for an unfinished
model — it's the permanent design, because a wrong sentence spoken to a
bank teller or a nurse is a real-world risk, not just a UX rough edge.

### Step by step

1. **Capture, entirely client-side.** The browser runs the camera and
   MediaPipe Holistic locally. **Only landmark coordinates are ever
   sent to the backend — never a video frame or image.** This is a
   deliberate privacy choice: a public workplace is not a place people
   expect to be filmed and transmitted, and this design makes that a
   non-issue structurally rather than a policy promise.

2. **Transport — WebSocket** (`app/routers/recognize.py`,
   `/recognize/ws`). Wire protocol:
   - Client sends `{"type": "landmarks", "frame": {...}}` per captured
     frame, `{"type": "pause"}` when the signer visibly stops (forces an
     immediate recognition attempt on whatever's buffered), or
     `{"type": "reset"}` to clear the buffer for a new sentence.
   - Server responds `{"type": "result", "status": ..., "gloss_sequence":
     [...], "sentence_text": "...", "recognition_id": ...}` after each
     frame.
   - Client sends `{"type": "confirm", "recognition_id": ...,
     "corrected_text": ...}` once the signer approves (or edits) what
     was recognized — `corrected_text` is `null` if they approved as-is.

3. **Buffering** (`app/services/recognition.py`, `SignRecognizer`) —
   one instance per WebSocket connection, holding a rolling window of
   the most recent frames (capped at 300, ~12 seconds at 25fps, to
   bound memory on a long session). A recognition attempt needs at
   least 15 buffered frames; below that, the response status is
   `"buffering"` rather than a guess.

4. **Recognition — the actual gap.** `_run_inference()` is where a
   trained model would turn the buffered landmark window into a gloss
   sequence. **It currently raises `NotImplementedError` on purpose.**
   There is no model to load yet, so rather than return placeholder or
   invented gloss output, every request honestly reports
   `status: "recognizer_not_loaded"`. Once a model exists:
   - Set `RECOGNIZER_MODEL_PATH` in `.env`.
   - Implement `_load_model()` (ONNX Runtime is assumed by the current
     code shape — swap for PyTorch/TF if the trained model isn't ONNX).
   - Implement `_run_inference()` to return a `List[str]` of gloss tags.
   - Nothing else changes — buffering, the WebSocket protocol, session
     logging, and sentence assembly already expect exactly that return
     shape.

5. **Gloss → sentence** (`app/services/gloss_to_text.py`), two layers,
   mirroring Pipeline A's approach:
   - **`assemble_sentence()`** — rule-based, offline, always available.
     It's the inverse of the local engine's ordering: a trailing
     WH-tag moves back to the front and forms a question; a trailing
     `NO` becomes "not" negating what came before; otherwise the words
     are joined in order, since ISL's topic-comment order reads close
     enough to English for short kiosk phrases.
   - **`assemble_sentence_smart()`** — if `GROQ_API_KEY` is set, sends
     the gloss sequence and the rule-based draft to Groq to naturalize
     into a more fluent sentence, with a 3-second timeout and the
     rule-based draft as the fallback on any failure. With no key set,
     this is just the rule-based version — verified to behave
     identically either way.

6. **Storage** — `recognition_sessions` table: one row per recognition
   attempt (gloss sequence, assembled sentence, confidence, whether it
   was confirmed, and any correction the signer made). This table is
   also where future training/eval data for the recognizer accumulates,
   since every human correction is a labeled example.

7. **Output.** Once confirmed, `sentence_text` is spoken through the
   browser's speech synthesis API — the backend never generates audio
   server-side.

### What Pipeline B needs to be complete

A trained sign-recognition model. Two realistic approaches, not
mutually exclusive:
- **Isolated-sign recognition** first (a Transformer or BiLSTM over
  normalized landmark sequences), which is the easier problem and
  reuses the same CISLR + team-recorded data as Pipeline A's vocabulary
  work.
- **Continuous recognition** (segmentation or a CTC-style model) as the
  harder, longer-term step once isolated recognition works.

This is the real bottleneck for Pipeline B specifically because
continuous ISL training data is scarce — structured recording sessions
with Deaf signers, planned early, are what actually unblocks this.
Everything downstream of `_run_inference()` is already built and tested.
