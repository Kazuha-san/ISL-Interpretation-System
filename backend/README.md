# ISL Kiosk Translation - Backend

## Current Status: v0.1.0 (Initial Scaffolding)

### Overview

This backend provides the API layer for an Indian Sign Language (ISL) kiosk translation system. The system converts Hindi/English transcripts into ISL gloss using the Groq API with Llama 3.1 8B.

### What's Implemented

#### Core Infrastructure
- ✅ FastAPI application with CORS middleware (Vite dev server at localhost:5173)
- ✅ SQLite database with WAL mode for resilience
- ✅ 50 vocabulary entries pre-seeded in the database
- ✅ Environment configuration via `.env` file

#### Services
- ✅ **Gloss Service** (`app/services/gloss.py`)
  - Converts Hindi/English to ISL gloss using Groq API
  - Implements ISL grammar rules (topic-comment order, drops articles/copulas, etc.)
  - Dynamic vocabulary mapping from database
  - Supports context-aware conversion (general, banking, health, identity)

#### Routers (Stubbed/Partial)
- ✅ `/translate` - Full implementation with `/forward` and `/test` endpoints
- ✅ `/vocabulary` - Health check stub
- ✅ `/qna` - Health check stub
- ✅ `/session` - Health check stub
- ✅ `/sync` - Health check stub

#### Models & Utilities
- ✅ Empty model stubs for vocabulary, session, qna, staff
- ✅ Service stubs for ASR, TTS, fingerspell, retrieval
- ✅ Utility helper files ready for implementation

### What's Not Yet Implemented

- ❌ ASR (Automatic Speech Recognition) service for ISL fingerspelling
- ❌ TTS (Text-to-Speech) service
- ❌ Cloud database synchronization with Supabase
- ❌ Session tracking and management
- ❌ Q&A logging and retrieval
- ❌ Staff progress tracking

### Database Schema

The `vocabulary` table contains:
- `id` - Primary key
- `word_en` - English word
- `word_hi` - Hindi translation
- `gloss_tag` - ISL gloss identifier (unique)
- `category` - Word category (e.g., greetings, identity, documents)

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your GROQ_API_KEY and other settings

# 3. Initialize database
python run.py
# Database will be auto-initialized on startup

# 4. Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/translate/test
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Global health check |
| GET | `/translate/health` | Translate service health |
| POST | `/translate/forward` | Convert transcript to ISL gloss |
| GET | `/translate/test` | Test translation with sample input |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key for Llama 3.1 8B model |
| `SUPABASE_URL` | No | Supabase project URL (for future cloud sync) |
| `SUPABASE_KEY` | No | Supabase API key (for future cloud sync) |
| `WHISPER_MODEL` | No | Whisper model for ASR (default: "base") |
| `KIOSK_ID` | No | Kiosk identifier (default: "kiosk_dev_01") |
| `KIOSK_LOCATION` | No | Kiosk location (default: "Development") |

### Development Notes

- The gloss service requires a valid Groq API key to function
- Vocabulary IDs are fetched dynamically from the database on each request
- ISL grammar rules are strictly applied in the gloss conversion prompt
- The database schema is versioned and idempotent (safe to re-run)

### Next Steps

1. Implement ASR service for ISL fingerspelling recognition
2. Implement TTS service for audio output
3. Connect to Supabase for cloud synchronization
4. Implement session tracking with kiosk integration
5. Build Q&A logging and retrieval functionality
6. Add staff progress tracking and analytics