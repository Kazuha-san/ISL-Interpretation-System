# ISL Interpreter — Project Overview

## What this is

A two-way Indian Sign Language (ISL) interpreter for general public-facing
workplaces — offices, hospitals, banks, government counters, and similar
settings where a hearing staff member and a Deaf person need to
communicate without a human interpreter present.

It runs as standalone, installable software on a single on-prem machine
per location. There is no cloud backend, no accounts, and no multi-site
sync — each install is self-contained.

## Scope

The system is two interpreters in one, corresponding to the two
directions a conversation needs:

- **Pipeline A — hearing → Deaf.** The hearing person speaks or types.
  The system converts that into ISL gloss and plays it back as a signing
  3D avatar, including facial expression, which carries real ISL grammar
  (question marking, negation) and isn't just decoration.
- **Pipeline B — Deaf → hearing.** The Deaf person signs in front of a
  camera. The system recognizes the signs, assembles them into an
  English sentence, shows it to the signer for confirmation, and speaks
  it aloud once confirmed.

Both pipelines are in scope and being built in parallel — this is a
change from an earlier plan that treated the project as Pipeline A only
(a one-directional interpreter, like a TV sign-language interpreter) with
Pipeline B deferred indefinitely. There is no hard deadline driving this;
the two pipelines are being built to be genuinely correct rather than
demo-scripted.

### What's explicitly out of scope right now

- Free, unbounded conversation. Pipeline A works from a defined
  vocabulary plus an LLM fallback for phrasing it doesn't recognize —
  it is a bounded-domain tool, not a general interpreter.
- Cloud sync, multi-device/multi-kiosk coordination, accounts, or
  payments. Nothing here needs them, and adding them would be
  unjustified complexity for a single-machine install.
- Server-side speech recognition or synthesis. Both run client-side
  through the browser's Web Speech API, so the backend never handles
  raw audio.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python) | Async-friendly, plays well with WebSockets for Pipeline B's live landmark stream |
| Database | SQLite (WAL mode) | Single on-prem machine, no multi-site sync need — a cloud database (Supabase) was evaluated and removed for having no real use case here |
| Gloss engine (A) | Deterministic rule-based engine, local | Applies ISL grammar rules (topic-comment order, WH-word/negation placement, dropped articles/copulas) without needing an LLM or network |
| Online fallback (A & B) | Groq (Llama 3.1 8B) | Optional — used only when the local engine's confidence is low or to naturalize Pipeline B's recognized sentences; the whole system works with no API key at all |
| Avatar | Ready Player Me rig + Three.js playback | Chosen specifically for ARKit facial blendshapes, which a plain Mixamo auto-rig doesn't have, needed because facial expression is grammatical in ISL, not cosmetic |
| Sign extraction | MediaPipe (pose, both hands, face) | Produces the keypoint JSON that drives both the avatar (Pipeline A) and, eventually, recognition training data (Pipeline B) |
| Sign recognition (B) | Camera-based, landmarks-only over WebSocket | Only landmark coordinates leave the browser, never video — a deliberate privacy choice for a public workplace setting |
| Frontend | Not yet built | A separate design/frontend teammate is bringing this; backend is built API-first so frontend work can start independently |

## Current status

- **Pipeline A:** gloss conversion works end to end offline against the
  current pilot vocabulary (44 of 51 target words; the rest weren't
  available in any source checked so far). Avatar playback is blocked on
  real keypoint data — the ISLRTC public ISL dictionary is the planned
  source for expanding vocabulary at scale, alongside the team's own
  MediaPipe extraction work.
- **Pipeline B:** the full data path is built — landmark streaming,
  buffering, gloss-to-sentence assembly (rule-based, with optional Groq
  smoothing), and a confirm-before-speaking step — but there is no
  trained recognition model yet. That's the team's next major piece of
  work; the code is structured so the model is the only thing left to
  plug in once it exists.
- **Backend infrastructure:** cleaned up and audited — no cloud
  dependency, no hardcoded secrets, no dead stub code left unexplained.
  See `PIPELINES.md` for the full technical breakdown of how both
  pipelines actually work.
