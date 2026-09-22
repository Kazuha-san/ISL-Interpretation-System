"""
app/services/gloss_to_text.py

Pipeline B's counterpart to local_gloss.py: turns a recognized ISL gloss
sequence back into a readable English sentence for the hearing person to
read/hear.

Two-layer approach, same philosophy as Pipeline A's convert_to_gloss_smart:
1. assemble_sentence() — deterministic, offline, rule-based. Inverse of
   local_gloss.py's _apply_gloss_ordering (WH-word/NO moved to the end for
   signing, moved back here) plus simple templates for what ISL drops
   (copulas, articles). Always available, zero dependencies.
2. assemble_sentence_smart() — if GROQ_API_KEY is set, asks Groq to turn
   the same gloss sequence into a more natural sentence, with the
   rule-based version as both the prompt's anchor and the fallback if
   Groq is unreachable or times out. If no key is set, this is just
   assemble_sentence() — no behavior change, no crash.

Either way, the result is shown to the signer for confirmation
(recognition_sessions.confirmed) before it's spoken — smoothing reduces
how much editing that confirmation step usually needs, it doesn't remove
the need for it.
"""
import asyncio
import logging
from typing import List, Optional

from ..config import settings
from ..database.local_db import get_connection

logger = logging.getLogger(__name__)

WH_TAGS = {"WHAT", "WHERE", "WHEN", "WHO", "HOW_MUCH", "WHICH"}
WH_WORDS = {
    "WHAT": "what", "WHERE": "where", "WHEN": "when",
    "WHO": "who", "HOW_MUCH": "how much", "WHICH": "which",
}

GROQ_TIMEOUT_SECONDS = 3.0

SMOOTHING_SYSTEM_PROMPT = """You rewrite a rough, rule-based English draft of a \
sentence a Deaf ISL signer just signed into a natural, grammatical English \
sentence with the same meaning. You are given the original ISL gloss sequence \
for context and the rough draft.

Rules:
- Keep the meaning exactly. Never add information that isn't implied by the gloss.
- Keep it short — this is spoken back immediately at a workplace counter.
- If the draft is already a question (ends in "?"), keep it a question.
- Output ONLY the corrected sentence. No preamble, no quotes, no explanation.
"""


def _gloss_tag_to_word(tag: str) -> str:
    """Look up the vocabulary table for a human-readable word for a gloss tag.
    Falls back to a lowercased/underscore-stripped version of the tag itself
    (e.g. fingerspelled proper nouns won't be in the vocabulary table)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT word_en FROM vocabulary WHERE gloss_tag = ?", (tag,)
        ).fetchone()
        if row:
            return row[0]
        return tag.replace("_", " ").lower()
    finally:
        conn.close()


def assemble_sentence(gloss_sequence: List[str]) -> str:
    """
    Convert a recognized gloss sequence (already in ISL sign order — topic
    first, WH-word/negation at the end) into an English sentence.

    Rules (inverse of local_gloss.py's ordering):
    1. If a WH-tag is present at the end, move it to the front and form a
       question ("What ...?").
    2. If NO is present, render as "not" negating the content before it,
       and drop the trailing NO tag from the word sequence.
    3. Otherwise, just join the words in order — ISL's topic-comment order
       reads close enough to English word order for short kiosk phrases
       that this is left alone rather than guessing at grammar it can't
       verify without a language model.
    """
    if not gloss_sequence:
        return ""

    tags = list(gloss_sequence)
    is_negated = False
    wh_word = None

    if tags and tags[-1] in WH_TAGS:
        wh_word = WH_WORDS[tags.pop()]
    if tags and tags[-1] == "NO":
        is_negated = True
        tags.pop()

    words = [_gloss_tag_to_word(t) for t in tags]

    if wh_word:
        sentence = f"{wh_word} " + " ".join(words) if words else wh_word
        sentence = sentence.strip() + "?"
    elif is_negated:
        sentence = ("not " + " ".join(words)).strip() + "."
    else:
        sentence = " ".join(words).strip()
        if sentence:
            sentence += "."

    return sentence[0].upper() + sentence[1:] if sentence else sentence


async def _smooth_with_groq(gloss_sequence: List[str], draft: str) -> Optional[str]:
    """Ask Groq to naturalize the rule-based draft. Returns None on any
    failure (unreachable, timeout, bad key, malformed reply) so the caller
    can fall back to the draft — this must never raise."""
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)

        user_prompt = (
            f"ISL gloss sequence: {' '.join(gloss_sequence)}\n"
            f"Rough draft: {draft}\n"
            f"Corrected sentence:"
        )

        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SMOOTHING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=100,
            ),
            timeout=GROQ_TIMEOUT_SECONDS,
        )
        text = response.choices[0].message.content.strip()
        return text if text else None
    except Exception as e:
        logger.info(f"Groq smoothing unavailable, using rule-based draft: {e}")
        return None


async def assemble_sentence_smart(gloss_sequence: List[str]) -> dict:
    """
    Two-layer sentence assembly for a recognized gloss sequence.

    Returns:
        {"sentence_text": str, "source": "groq" | "rule_based", "draft": str}
        "draft" is always the rule-based output, even when Groq is used —
        useful for the confirm/correct UI to show what changed.
    """
    draft = assemble_sentence(gloss_sequence)

    if not settings.groq_enabled or not gloss_sequence:
        return {"sentence_text": draft, "source": "rule_based", "draft": draft}

    smoothed = await _smooth_with_groq(gloss_sequence, draft)
    if smoothed:
        return {"sentence_text": smoothed, "source": "groq", "draft": draft}
    return {"sentence_text": draft, "source": "rule_based", "draft": draft}
