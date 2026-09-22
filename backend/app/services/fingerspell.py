"""
app/services/fingerspell.py

Minimal implementation for fingerspelling support.
Returns clip path references for fingerspell sequences.

Assumptions:
- Fingerspell clips are at assets/fingerspell/{LETTER}.mp4
- No keypoint JSON for fingerspell (videos only)
- Returns a placeholder sequence structure compatible with retrieval
"""

from typing import Dict, List
from pathlib import Path

from ..config import settings


# Fingerspell clip path template
# Expected: assets/fingerspell/A.mp4, assets/fingerspell/B.mp4, etc.
FINGERSPELL_CLIPS_DIR = Path("assets/fingerspell")


def get_fingerspell_clip_path(letter: str) -> str:
    """
    Get the clip path for a single letter.
    
    Args:
        letter: Single uppercase letter (A-Z)
        
    Returns:
        Path to the MP4 file (relative to project root)
    """
    return f"{FINGERSPELL_CLIPS_DIR}/{letter.upper()}.mp4"


def get_fingerspell_sequence(text: str) -> Dict:
    """
    For a fingerspell-type token, split into letters and build
    a sequence-shaped dict compatible with retrieval output.
    
    Args:
        text: Text to fingerspell (e.g., "HELLO" or proper noun)
        
    Returns:
        Sequence dict with:
        - word: the original text
        - fps: 25 (standard frame rate)
        - frames: list of frame data (mock data with letter info)
        - duration_ms: estimated duration in milliseconds
        - display_text: the text in uppercase for display
    """
    # Get uppercase letters only
    letters = [c.upper() for c in text if c.isalpha()]
    
    # Build frame data - each letter gets its own frame
    # In a real implementation, this would load keypoint data from video
    frames = []
    for i, letter in enumerate(letters):
        # Placeholder frame with letter reference
        frames.append({
            "frame_index": i,
            "letter": letter,
            "clip_path": get_fingerspell_clip_path(letter),
            "is_fingerspell": True
        })
    
    # Compute duration - assume 500ms per letter (standard sign language fingerspelling speed)
    fps = 25
    frame_count = len(frames) if frames else 10  # At least 10 frames for placeholder
    duration_ms = int((frame_count / fps) * 1000) if fps else 0
    display_text = text.upper()
    
    return {
        "word": text.upper(),
        "fps": fps,
        "frames": frames,
        "duration_ms": duration_ms,
        "display_text": display_text
    }


def is_valid_fingerspell_input(text: str) -> bool:
    """
    Check if text is suitable for fingerspelling (mostly letters, no spaces).
    
    Args:
        text: Text to check
        
    Returns:
        True if text is suitable for fingerspelling
    """
    # Allow mostly alphabetic content, minimal numbers/special chars
    alpha_count = sum(1 for c in text if c.isalpha())
    return alpha_count >= len(text) * 0.8 if text else False