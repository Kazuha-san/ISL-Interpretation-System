"""
app/services/retrieval.py

Retrieval service for sign clips and keypoint sequences.
Handles both vocab-based sign retrieval and fingerspell sequences.

IMPORTANT: MOCK_KEYPOINTS mode
-------------------------------
When MOCK_KEYPOINTS=True (default), this service returns synthetic
placeholder sequences instead of reading real keypoint JSON files.
This allows end-to-end testing before real keypoint data is available.

Set MOCK_KEYPOINTS=false in .env once real keypoint JSON files are
seeded into sign_clips table and assets/clips/keypoints/ directory.

When MOCK_KEYPOINTS=False, the service reads real keypoint files:
- Reads keypoint_json_path from sign_clips table
- Parses the JSON file at that path
- Returns None gracefully if file is missing (no crash)

File structure expected for real keypoint data:
assets/clips/keypoints/{word}.json

Where {word}.json contains:
{
    "word": "hello",
    "fps": 25.0,
    "frame_count": 42,
    "frames": [
        {
            "pose": [[x, y, z], ...33 items],
            "left_hand": [[x, y, z], ...21 items],
            "right_hand": [[x, y, z], ...21 items],
            "face_blendshapes": {"browDownLeft": 0.02, "jawOpen": 0.15, ...}
        }
    ]
}

Note: Each frame has pose, left_hand, right_hand, and face_blendshapes keys.
This is the real schema produced by the video-processing pipeline.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from .gloss import convert_to_gloss
from ..config import settings
from ..database.local_db import get_connection

# Configure logger
logger = logging.getLogger(__name__)

# Assets directory paths
KEYPOINTS_DIR = Path("assets/clips/keypoints")
FINGERSPELL_DIR = Path("assets/fingerspell")


def _get_vocabulary_word(conn: Any, vocab_id: int) -> Optional[str]:
    """
    Get word_en from vocabulary table by id.
    
    Args:
        conn: SQLite connection
        vocab_id: Vocabulary table ID
        
    Returns:
        word_en string or None if not found
    """
    cursor = conn.execute(
        "SELECT word_en FROM vocabulary WHERE id = ?",
        (vocab_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _get_sign_clip(conn: Any, vocab_id: int) -> Optional[Dict]:
    """
    Get sign clip info from sign_clips table.
    
    Args:
        conn: SQLite connection
        vocab_id: Vocabulary table ID
        
    Returns:
        Dict with keypoint_json_path or None if not found
    """
    cursor = conn.execute(
        """
        SELECT id, video_url, keypoint_json_path, duration_ms, signer_ref
        FROM sign_clips
        WHERE vocabulary_id = ?
        """,
        (vocab_id,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "video_url": row[1],
        "keypoint_json_path": row[2],
        "duration_ms": row[3],
        "signer_ref": row[4]
    }


async def _read_keypoint_file_async(file_path: str) -> Optional[Dict]:
    """
    Read and parse keypoint JSON file asynchronously.
    
    Args:
        file_path: Path to JSON file (relative to project root)
        
    Returns:
        Parsed JSON dict or None if file missing/cannot parse
    """
    try:
        path = Path(file_path)
        # Handle relative paths
        if not path.is_absolute():
            # Try relative to current working directory first
            if not path.exists():
                # Try relative to app directory
                path = Path(__file__).parent.parent / file_path
        
        if not path.exists():
            logger.warning(f"Keypoint file not found: {file_path}")
            return None
        
        # Use asyncio.to_thread for sync file I/O
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None,
            lambda: path.read_text(encoding='utf-8')
        )
        
        data = json.loads(content)
        
        # Validate schema: check that frames[0] has 'pose' key if frames exist
        frames = data.get("frames", [])
        if frames and "pose" not in frames[0]:
            logger.warning(
                f"Keypoint file {file_path} appears to have wrong schema. "
                f"First frame missing 'pose' key. Expected: {{pose, left_hand, right_hand, face_blendshapes}}"
            )
        
        return data
        
    except Exception as e:
        logger.warning(f"Failed to read keypoint file {file_path}: {e}")
        return None


def _build_mock_sequence(word: str) -> Dict[str, Any]:
    """
    Build a synthetic placeholder sequence for mock mode.
    
    Args:
        word: Word to include in sequence
        
    Returns:
        Sequence dict with mock frame data
    """
    frame_count = 10
    fps = 25
    duration_ms = int((frame_count / fps) * 1000) if fps else 0
    display_text = word.replace("_", " ").title()
    
    return {
        "word": word,
        "fps": fps,
        "frames": [
            {"mock": True, "frame_index": i}
            for i in range(frame_count)
        ],
        "duration_ms": duration_ms,
        "display_text": display_text
    }


async def get_sequence_for_vocab_id(vocab_id: int) -> Optional[Dict]:
    """
    Look up sign_clips WHERE vocabulary_id = vocab_id.
    
    In MOCK_KEYPOINTS mode: returns synthetic placeholder sequence.
    
    In real mode: reads keypoint_json_path from sign_clips, parses
    the JSON file, and returns the sequence. Returns None if no clip
    found or file missing (caller decides fallback behavior).
    
    Args:
        vocab_id: Vocabulary table ID
        
    Returns:
        Sequence dict with word, fps, frames or None if not found
    """
    conn = get_connection()
    try:
        # Get word from vocabulary
        word = _get_vocabulary_word(conn, vocab_id)
        if not word:
            logger.debug(f"No vocabulary entry found for id={vocab_id}")
            return None
        
        # Get sign clip info
        clip_info = _get_sign_clip(conn, vocab_id)
        if not clip_info:
            logger.debug(f"No sign clip found for vocab_id={vocab_id}")
            return None
        
        if settings.MOCK_KEYPOINTS:
            # Return synthetic placeholder
            logger.debug(f"MOCK_KEYPOINTS=True: returning placeholder for {word}")
            return _build_mock_sequence(word)
        
        # Real mode: read keypoint file
        keypoint_path = clip_info.get("keypoint_json_path")
        if not keypoint_path:
            logger.debug(f"No keypoint_json_path for vocab_id={vocab_id}")
            return None
        
        # Read and parse the JSON file
        keypoint_data = await _read_keypoint_file_async(keypoint_path)
        if keypoint_data is None:
            logger.warning(f"Keypoint file missing or invalid: {keypoint_path}")
            return None
        
        # Build sequence from real data
        frame_count = len(keypoint_data.get("frames", []))
        fps = keypoint_data.get("fps", 25)
        duration_ms = int((frame_count / fps) * 1000) if fps else 0
        display_text = word.replace("_", " ").title()
        
        return {
            "word": word,
            "fps": fps,
            "frames": keypoint_data.get("frames", []),
            "duration_ms": duration_ms,
            "display_text": display_text
        }
        
    finally:
        conn.close()


async def get_fingerspell_sequence(text: str) -> Dict[str, Any]:
    """
    For a fingerspell-type token, split into letters, look up each
    letter's clip reference, and return a sequence-shaped dict.
    
    Args:
        text: Text to fingerspell (e.g., "HELLO" or proper noun)
        
    Returns:
        Sequence dict with word, fps, frames (may be empty if no letters)
    """
    # Use fingerspell service for clip paths
    from .fingerspell import get_fingerspell_sequence as fs_sequence
    
    # Get the base sequence
    sequence = fs_sequence(text)
    
    if settings.MOCK_KEYPOINTS:
        # Replace with mock frames if in mock mode
        return _build_mock_sequence(text)
    
    return sequence


async def resolve_tokens_to_sequences(tokens: List[Dict]) -> Dict[str, Any]:
    """
    Given the `tokens` list from convert_to_gloss(), resolve each
    token to a sequence.
    
    - type "vocab" or "paraphrase" -> get_sequence_for_vocab_id(token["vocab_id"])
    - type "fingerspell" -> get_fingerspell_sequence(token["word"])
    
    Args:
        tokens: List of token dicts from gloss conversion
        
    Returns:
        {
            "sequences": [<seq or None for each token, in order>],
            "fallbacks": [<list of token words where lookup failed>]
        }
    """
    sequences = []
    fallbacks = []
    
    for token in tokens:
        token_word = token.get("word", "")
        token_type = token.get("type", "")
        
        if token_type == "fingerspell":
            # Fingerspell: get sequence from fingerspell service
            sequence = await get_fingerspell_sequence(token_word)
            sequences.append(sequence)
            
            # Check if we got valid data
            if not sequence or not sequence.get("frames"):
                fallbacks.append(token_word)
                
        elif token_type in ("vocab", "paraphrase"):
            # Regular vocab: look up by vocab_id
            vocab_id = token.get("vocab_id")
            if vocab_id is None:
                logger.warning(f"Token missing vocab_id: {token}")
                fallbacks.append(token_word)
                sequences.append(None)
                continue
            
            sequence = await get_sequence_for_vocab_id(vocab_id)
            sequences.append(sequence)
            
            if sequence is None:
                fallbacks.append(token_word)
                
        else:
            # Unknown type: skip
            logger.warning(f"Unknown token type: {token_type}, word={token_word}")
            sequences.append(None)
            fallbacks.append(token_word)
    
    return {
        "sequences": sequences,
        "fallbacks": fallbacks
    }


async def init() -> None:
    """
    Initialize the retrieval service.
    
    Logs whether mock mode is active at startup so it's clear
    whether real file I/O or synthetic data will be used.
    """
    if settings.MOCK_KEYPOINTS:
        print("[retrieval] MOCK_KEYPOINTS=True — returning placeholder sequences")
    else:
        print("[retrieval] MOCK_KEYPOINTS=False — reading real keypoint files")