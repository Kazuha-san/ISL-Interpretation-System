"""
Service for converting Hindi/English transcripts to ISL gloss using Groq API.
Implements the system prompt from gloss_prompt.md with vocabulary lookup.
"""

import json
import asyncio
import httpx
import sqlite3
import logging
from typing import Any, Dict, List, Optional, TypedDict, Literal
from groq import Groq
from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)


class GlossToken(TypedDict):
    """Token structure for gloss conversion output."""
    word: str
    type: Literal["vocab", "paraphrase", "fingerspell"]
    vocab_id: Optional[int]
    source_word: Optional[str]


class GlossResult(TypedDict):
    """Result structure for gloss conversion."""
    gloss: List[str]
    tokens: List[GlossToken]


class GlossService:
    """Service for converting transcripts to ISL gloss."""
    
    # System prompt from gloss_prompt.md
    SYSTEM_PROMPT = """You are an ISL (Indian Sign Language) gloss conversion engine. You convert
spoken Hindi or English sentences into ISL gloss — the sequence of signs
a fluent ISL signer would produce for the same meaning.

## ISL GRAMMAR RULES (apply strictly)

1. Word order: topic-comment. Move the object before the verb.
   Example: "What is your name" -> NAME WHAT (topic NAME, then question word)
2. Drop all articles (a, an, the) - they have no ISL equivalent.
3. Drop all auxiliary verbs (is, are, was, were, am) - not signed in ISL.
4. Drop copula / linking verbs entirely.
5. Negation: sign the main content first, then NO at the end.
   Example: "I don't understand" -> UNDERSTAND NO
6. Questions: sign the content words first, WH-word (WHAT/WHERE/WHEN/WHO/
   HOW_MUCH/WHICH) goes at the END of the gloss sequence.
7. Numbers are signed as individual digit signs in sequence.

## AVAILABLE VOCABULARY (gloss_tags you may use)

HELLO, GOOD_MORNING, THANK_YOU, PLEASE, SORRY, WELCOME, YES, NO,
NAME, AGE, ADDRESS, ID_CARD, DATE_OF_BIRTH, MALE, FEMALE,
WAIT, NEXT, HELP, REPEAT, UNDERSTOOD, TOMORROW,
FORM, DOCUMENT, CERTIFICATE, PHOTOCOPY, PHOTO, APPOINTMENT, RECEIPT,
ONE, TWO, THREE, FOUR, FIVE, SIX, SEVEN, EIGHT, NINE, TEN,
WHAT, WHERE, WHEN, WHO, HOW_MUCH, WHICH

Use ONLY these gloss_tags for type "vocab" tokens. Never invent a tag
that is not in this list.

## TOKEN TYPES

- "vocab"     : word maps directly to a gloss_tag above. Include its vocab_id.
- "paraphrase": word is not in the vocabulary but a close equivalent is.
                Map to the nearest vocab_id and explain via the "source_word" field.
- "fingerspell": word has no vocabulary match and no close equivalent
                (proper nouns, specific ID numbers, place names, uncommon
                words). Provide the literal string to fingerspell letter
                by letter.

## OUTPUT FORMAT — STRICT

Return ONLY valid JSON. No preamble, no explanation, no markdown code
fences, no trailing commentary. The JSON must match this exact schema:

{
  "gloss": ["<gloss_tag_or_literal>", ...],
  "tokens": [
    {
      "word": "<gloss_tag or literal string>",
      "type": "vocab" | "paraphrase" | "fingerspell",
      "vocab_id": <integer, only if type is vocab or paraphrase>,
      "source_word": "<original word, only if type is paraphrase>"
    }
  ]
}

If the input is empty or contains no translatable content, return:
{"gloss": [], "tokens": []}

## SESSION CONTEXT MODIFIERS (appended per request)

When a session context is provided, prefer vocabulary from these sets
when a word could map to more than one sign:

- banking:  FORM, DOCUMENT, RECEIPT, FEE, NUMBER
- health:   APPOINTMENT, CERTIFICATE, PHOTO
- identity: ID, NAME, AGE, ADDRESS, DATE_OF_BIRTH
- general:  no preference override

Context does not restrict which words CAN be used — only which one wins
when a sentence is ambiguous between two valid options.
"""
    
    # Context sets for preference
    # TODO: education context — currently uses general's empty override
    # Decide on specific education-related vocabulary if needed
    CONTEXT_SETS = {
        "banking": ["FORM", "DOCUMENT", "RECEIPT"],
        "health": ["APPOINTMENT", "CERTIFICATE", "PHOTO"],
        "identity": ["ID_CARD", "NAME", "AGE", "ADDRESS", "DATE_OF_BIRTH"],
        "education": [],  # Reuse general vocabulary for now
        "general": []
    }
    
    def __init__(self):
        """Initialize Groq client with API key from settings.

        Raises only when actually called without a key configured — callers
        (convert_to_gloss_smart) check settings.groq_enabled first and skip
        this path entirely when running offline, so this is a safeguard,
        not the normal offline code path.
        """
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. This call path requires the online "
                "Groq fallback; use convert_to_gloss_smart() instead, which "
                "skips Groq automatically when no key is configured."
            )
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = "llama-3.1-8b-instant"  # Llama 3.1 8B as specified
    
    def _get_vocabulary_map(self, connection: sqlite3.Connection) -> Dict[str, int]:
        """Get gloss_tag to id mapping from vocabulary table."""
        cursor = connection.execute("SELECT gloss_tag, id FROM vocabulary")
        return {row[0]: row[1] for row in cursor.fetchall()}
    
    def _build_context_prompt(self, 
                             context: Literal["general", "banking", "health", "identity"],
                             vocab_map: Dict[str, int],
                             transcript: str) -> str:
        """Build the complete prompt with context and vocabulary."""
        context_block = f"Session context: {context}\n"
        vocab_block = f"Vocabulary IDs for lookup:\n{json.dumps(vocab_map, indent=2)}\n\n"
        transcript_block = f"Transcript to convert:\n{transcript}"
        
        return self.SYSTEM_PROMPT + "\n\n" + context_block + vocab_block + transcript_block
    
    async def convert_to_gloss(
        self,
        transcript: str,
        context: Literal["general", "banking", "health", "identity"] = "general"
    ) -> GlossResult:
        """
        Convert transcript to ISL gloss using Groq API.
        
        Args:
            transcript: Hindi/English text to convert
            context: Session context for vocabulary preference
            
        Returns:
            GlossResult containing gloss sequence and token metadata
        """
        if not transcript.strip():
            return {"gloss": [], "tokens": []}
        
        # Get vocabulary mapping from database
        from app.database.local_db import get_connection
        connection = get_connection()
        try:
            vocab_map = self._get_vocabulary_map(connection)
        finally:
            connection.close()
        
        # Build the complete prompt
        prompt = self._build_context_prompt(context, vocab_map, transcript)
        
        try:
            # Call Groq API
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=500
            )
            
            # Parse the JSON response
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from response (handle potential extra text)
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                content = content[json_start:json_end]
            
            result = json.loads(content)
            
            # Validate result structure
            if "gloss" not in result or "tokens" not in result:
                raise ValueError("Invalid response format from Groq API")
            
            return result
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response from Groq API: {e}")
        except Exception as e:
            raise RuntimeError(f"Groq API call failed: {e}")


# Global service instance
_gloss_service: Optional[GlossService] = None


def get_gloss_service() -> GlossService:
    """Get or create the gloss service singleton."""
    global _gloss_service
    if _gloss_service is None:
        _gloss_service = GlossService()
    return _gloss_service


async def convert_to_gloss(
    transcript: str,
    context: Literal["general", "banking", "health", "identity"] = "general"
) -> GlossResult:
    """Convenience function to convert transcript to gloss."""
    service = get_gloss_service()
    return await service.convert_to_gloss(transcript, context)


# --- Smart gloss conversion with caching and offline support ---

async def convert_to_gloss_smart(
    transcript: str,
    context: Literal["general", "banking", "health", "identity", "education"] = "general",
    language: Literal["en", "hi"] = "en",
) -> Dict[str, Any]:
    """
    Smart resolution order:
    1. Exact match in resolved_phrases_cache (approved only)
    2. Local rule engine, if confidence HIGH -> use directly
    3. Groq, if reachable -> use its result, cache it (pending_review)
    4. Local rule engine best-effort (if MEDIUM/LOW confidence and Groq unreachable)
    5. Full fingerspell fallback (if local confidence was LOW and Groq unreachable)

    Returns the normal GlossResult dict, PLUS extra debug/transparency fields:
        "source": "cache" | "local_rule_engine" | "groq" | "fingerspell_fallback"
        "confidence": float | None
        "was_online": bool
    """
    from .local_gloss import convert_to_gloss_local
    from ..database.local_db import cache_lookup, cache_upsert
    
    # Normalize transcript for cache lookup
    def _normalize_for_cache(text: str) -> str:
        import re
        if language == "en":
            text = re.sub(r'[^\w\s]', '', text)
            text = text.lower()
        else:
            text = re.sub(r'[^\w\s\u0900-\u097F]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    normalized_input = _normalize_for_cache(transcript)
    
    # Step 1: Cache lookup (only approved entries)
    cached = cache_lookup(normalized_input, context)
    if cached:
        try:
            result = json.loads(cached["gloss_json"])
            if isinstance(result, dict) and "gloss" in result and "tokens" in result:
                cache_upsert(normalized_input, context, cached["gloss_json"], "groq")  # Update hit count
                return {
                    **result,
                    "source": "cache",
                    "confidence": None,
                    "was_online": False
                }
        except json.JSONDecodeError:
            logger.warning(f"Cache entry for '{normalized_input}' is malformed, skipping")
    
    # Step 2: Local rule engine (high confidence path)
    local_result = convert_to_gloss_local(transcript, language)
    if local_result["confidence"] >= 0.85:
        gloss_json = json.dumps(local_result["result"])
        cache_upsert(normalized_input, context, gloss_json, "local_rule_engine")
        return {
            **local_result["result"],
            "source": "local_rule_engine",
            "confidence": local_result["confidence"],
            "was_online": False
        }
    
    # Step 3: Groq attempt (only reached if local confidence < 0.85, and only
    # if a key is configured — this app must fully work with GROQ_API_KEY unset)
    GROQ_TIMEOUT_SECONDS = 3.0
    was_online = False

    if settings.groq_enabled:
        was_online = True
        try:
            from .gloss import convert_to_gloss as groq_convert
            result = await asyncio.wait_for(
                groq_convert(transcript, context),
                timeout=GROQ_TIMEOUT_SECONDS
            )

            # Cache Groq result as pending_review
            gloss_json = json.dumps(result)
            cache_upsert(normalized_input, context, gloss_json, "groq")

            return {
                **result,
                "source": "groq",
                "confidence": None,
                "was_online": True
            }

        except (httpx.ConnectError, httpx.TimeoutException, asyncio.TimeoutError):
            # Genuine offline / unreachable
            was_online = False
            logger.info(f"Groq unreachable, falling back to local rule engine for '{normalized_input}'")
        except Exception as e:
            # Some other failure (bad key, malformed response, etc.)
            logger.error(f"Groq call failed for non-connectivity reason: {e}")
            was_online = False
    else:
        logger.debug("GROQ_API_KEY not configured — skipping online fallback, using local engine only")
    
    # Step 4: Local best-effort (if Groq was unreachable or failed)
    # Use local result regardless of confidence
    if local_result["confidence"] >= 0.5:
        gloss_json = json.dumps(local_result["result"])
        cache_upsert(normalized_input, context, gloss_json, "local_rule_engine")
        return {
            **local_result["result"],
            "source": "local_rule_engine",
            "confidence": local_result["confidence"],
            "was_online": was_online
        }
    
    # Step 5: Full fingerspell fallback (if local confidence < 0.5 and Groq unreachable)
    # Fingerspell the entire original transcript word-by-word
    tokens_list = []
    gloss_tags = []
    
    if language == "en":
        import re
        normalized = re.sub(r'[^\w\s]', '', transcript).lower()
        words = normalized.split()
    else:
        import re
        normalized = re.sub(r'[^\w\s\u0900-\u097F]', '', transcript)
        words = normalized.split()
    
    for word in words:
        tokens_list.append({
            "word": word,
            "type": "fingerspell",
            "vocab_id": None,
            "source_word": word
        })
        gloss_tags.append(word)
    
    return {
        "gloss": gloss_tags,
        "tokens": tokens_list,
        "source": "fingerspell_fallback",
        "confidence": local_result["confidence"],
        "was_online": was_online
    }
