"""
Local rule-based gloss engine for offline-first ISL gloss conversion.

This module implements a deterministic gloss conversion engine that:
1. Matches tokens against the vocabulary table
2. Applies ISL grammar rules (topic-comment order, WH-word at end, NO at end)
3. Returns confidence scores for result reliability
4. Works entirely offline with no API dependencies
"""

import re
import sqlite3
from typing import Dict, List, Literal, Optional, TypedDict

from .gloss import GlossResult, GlossToken

# Filler words to drop before matching - carry no ISL gloss
ENGLISH_FILLERS = {
    "a", "an", "the",
    "is", "are", "am", "was", "were", "be", "been", "being",
    "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "your", "my", "our", "his", "her", "their",
    "of", "to",
}

# ⚠️ Hindi filler list - first draft, not verified against a fluent speaker
# Flag this explicitly in the PR/commit, and get someone Hindi-fluent to review
# before relying on it in the real demo
HINDI_FILLERS = {
    "है", "हैं", "था", "थे", "थी",
    "का", "की", "के", "को", "में", "से", "पर",
}

# WH-word tags that need special ordering (go to end)
WH_TAGS = {"WHAT", "WHERE", "WHEN", "WHO", "HOW_MUCH", "WHICH"}


class LocalGlossResult(TypedDict):
    """Result structure for local gloss conversion."""
    result: GlossResult
    confidence: float
    matched_count: int
    unmatched_count: int


def _get_vocabulary_map(connection: sqlite3.Connection) -> Dict[str, tuple]:
    """
    Get vocabulary mapping from database.
    
    Returns:
        Dict mapping word_en.lower() or word_hi -> (gloss_tag, id)
    """
    cursor = connection.execute(
        "SELECT word_en, word_hi, gloss_tag, id FROM vocabulary"
    )
    vocab_map = {}
    for row in cursor.fetchall():
        word_en, word_hi, gloss_tag, vocab_id = row
        # Add English version (lowercase for matching)
        if word_en:
            vocab_map[word_en.lower().strip()] = (gloss_tag, vocab_id)
        # Add Hindi version (no case folding for Hindi)
        if word_hi:
            vocab_map[word_hi.strip()] = (gloss_tag, vocab_id)
    return vocab_map


def _normalize_text(text: str, language: Literal["en", "hi"] = "en") -> str:
    """
    Normalize input text for matching.
    
    For English: strip punctuation, collapse whitespace, lowercase
    For Hindi: strip punctuation, collapse whitespace (no case folding)
    """
    # Remove punctuation (keep alphanumeric and whitespace)
    # Keep Hindi characters intact
    if language == "en":
        # English: remove all punctuation
        text = re.sub(r'[^\w\s]', '', text)
        text = text.lower()
    else:
        # Hindi: remove only ASCII punctuation, keep Devanagari
        text = re.sub(r'[^\w\s\u0900-\u097F]', '', text)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def _apply_gloss_ordering(
    all_tokens: List[tuple]
) -> List[tuple]:
    """
    Apply ISL grammar rules for word ordering.
    
    Rules:
    1. WH-word (WHAT/WHERE/WHEN/WHO/HOW_MUCH/WHICH) goes to the END
    2. NO (negation) goes to the END, after content words but before WH-word
    3. All other tokens stay in their original relative order
    
    Args:
        all_tokens: List of (token, gloss_tag, vocab_id, type) tuples
        
    Returns:
        Reordered list of (token, gloss_tag, vocab_id, type) tuples
    """
    if not all_tokens:
        return []
    
    # Identify WH-token and NO
    wh_index = None
    no_index = None
    
    for i, (_, gloss_tag, _, _) in enumerate(all_tokens):
        if gloss_tag in WH_TAGS:
            wh_index = i
        elif gloss_tag == "NO":
            no_index = i
    
    # Build ordered list (exclude WH and NO first)
    ordered_tokens = []
    for i, (token, gloss_tag, vocab_id, token_type) in enumerate(all_tokens):
        if i != wh_index and i != no_index:
            ordered_tokens.append((token, gloss_tag, vocab_id, token_type))
    
    # Add NO if present
    if no_index is not None:
        _, gloss_tag, vocab_id, token_type = all_tokens[no_index]
        ordered_tokens.append((None, gloss_tag, vocab_id, token_type))
    
    # Add WH if present (last)
    if wh_index is not None:
        _, gloss_tag, vocab_id, token_type = all_tokens[wh_index]
        ordered_tokens.append((None, gloss_tag, vocab_id, token_type))
    
    return ordered_tokens


def convert_to_gloss_local(
    transcript: str,
    language: Literal["en", "hi"] = "en"
) -> LocalGlossResult:
    """
    Convert transcript to ISL gloss using local rule-based engine.
    
    Args:
        transcript: Hindi/English text to convert
        language: "en" for English, "hi" for Hindi
        
    Returns:
        LocalGlossResult with gloss result, confidence, and counts
    """
    if not transcript.strip():
        return {
            "result": {"gloss": [], "tokens": []},
            "confidence": 0.0,
            "matched_count": 0,
            "unmatched_count": 0,
        }
    
    # Get vocabulary from database (single source of truth)
    from ..database.local_db import get_connection
    connection = get_connection()
    try:
        vocab_map = _get_vocabulary_map(connection)
        
        # Normalize and tokenize
        normalized = _normalize_text(transcript, language)
        tokens = normalized.split()
        
        # Filter out fillers
        if language == "en":
            fillers = ENGLISH_FILLERS
        else:
            fillers = HINDI_FILLERS
        
        non_filler_tokens = [t for t in tokens if t.lower() not in fillers]
        
        # Match tokens to vocabulary
        matched = []  # List of (source_token, (gloss_tag, vocab_id))
        unmatched = []  # List of source_token
        
        for token in non_filler_tokens:
            if token in vocab_map:
                matched.append((token, vocab_map[token]))
            else:
                unmatched.append(token)
        
        # Build list of all tokens with their properties
        all_tokens = []
        for token in non_filler_tokens:
            if token in vocab_map:
                gloss_tag, vocab_id = vocab_map[token]
                all_tokens.append((token, gloss_tag, vocab_id, "vocab"))
            else:
                all_tokens.append((token, None, None, "fingerspell"))
        
        # Apply ISL ordering rules
        ordered_tokens = _apply_gloss_ordering(all_tokens)
        
        # Build final result
        gloss_tags = []
        tokens_list = []
        
        for token, gloss_tag, vocab_id, token_type in ordered_tokens:
            if token_type == "vocab":
                gloss_tags.append(gloss_tag)
                tokens_list.append({
                    "word": gloss_tag,
                    "type": "vocab",
                    "vocab_id": vocab_id,
                    "source_word": None
                })
            else:
                # Fingerspell unmatched tokens
                gloss_tags.append(token)
                tokens_list.append({
                    "word": token,
                    "type": "fingerspell",
                    "vocab_id": None,
                    "source_word": token
                })
        
        # Calculate confidence
        content_token_count = len(matched) + len(unmatched)
        if content_token_count == 0:
            confidence = 0.0
        else:
            confidence = len(matched) / content_token_count
        
        return {
            "result": {
                "gloss": gloss_tags,
                "tokens": tokens_list
            },
            "confidence": confidence,
            "matched_count": len(matched),
            "unmatched_count": len(unmatched)
        }
        
    finally:
        connection.close()
