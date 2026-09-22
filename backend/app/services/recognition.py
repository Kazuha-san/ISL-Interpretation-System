"""
app/services/recognition.py

Pipeline B (Deaf -> hearing): turns a buffered sequence of MediaPipe
landmark frames into a recognized gloss sequence.

STATUS: no trained model ships with this repo yet. There is nothing to
fake here — recognizing continuous ISL from landmarks requires a model
trained on real signer data, which is the video/motion-capture work your
team is starting. Until RECOGNIZER_MODEL_PATH (see app/config.py) points
at real weights, this service runs in `stub` mode: it accepts and buffers
landmark frames exactly like the real thing will, so the frontend/WebSocket
plumbing can be built and tested now, but every recognize() call returns
an explicit "recognizer_not_loaded" result instead of an invented sentence.

When you have a trained model:
1. Implement `_load_model()` below to load your model from RECOGNIZER_MODEL_PATH
   (ONNX Runtime is assumed — swap for torch/tf if your model isn't ONNX).
2. Implement `_run_inference()` to turn a landmark window into gloss tokens.
3. Everything downstream (session logging, gloss_to_text, the WebSocket
   router) already expects this exact return shape, so nothing else changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from ..config import settings

logger = logging.getLogger(__name__)

# One landmark frame, matching the schema documented in retrieval.py:
# pose (33 points), left_hand (21), right_hand (21) — face optional for
# recognition (facial grammar matters more for generation than recognition
# of manual signs, so it's not required here, only pose+hands).
LandmarkFrame = dict


@dataclass
class RecognitionResult:
    gloss_sequence: List[str] = field(default_factory=list)
    sentence_text: str = ""
    confidence: Optional[float] = None
    status: str = "ok"  # "ok" | "recognizer_not_loaded" | "buffering"


class SignRecognizer:
    """
    Holds a per-connection landmark buffer and (once available) the loaded
    model. One instance per active WebSocket connection — see
    app/routers/recognize.py.
    """

    # Minimum frames to attempt a recognition pass. Real value depends on
    # your model's window size once trained; this is a placeholder.
    MIN_WINDOW_FRAMES = 15

    def __init__(self):
        self.buffer: List[LandmarkFrame] = []
        self.model = self._load_model() if settings.recognizer_enabled else None

    def _load_model(self):
        """
        Load the trained recognizer from settings.RECOGNIZER_MODEL_PATH.
        Not implemented yet — no model exists to load. Replace this with
        real ONNX Runtime (or equivalent) loading code once training
        produces weights.
        """
        logger.warning(
            "RECOGNIZER_MODEL_PATH is set but _load_model() is not implemented yet."
        )
        return None

    def add_frame(self, frame: LandmarkFrame) -> None:
        self.buffer.append(frame)
        # Keep a rolling window so long sessions don't grow memory unbounded.
        # 300 frames at ~25fps is 12s of context — adjust once you know your
        # model's real receptive field.
        if len(self.buffer) > 300:
            self.buffer.pop(0)

    def reset(self) -> None:
        self.buffer.clear()

    async def recognize(self) -> RecognitionResult:
        """
        Attempt to recognize the current buffer. Called on each new frame
        (or on an explicit "signer paused" signal) by the WebSocket router.
        """
        if self.model is None:
            return RecognitionResult(status="recognizer_not_loaded")

        if len(self.buffer) < self.MIN_WINDOW_FRAMES:
            return RecognitionResult(status="buffering")

        gloss_sequence = self._run_inference(self.buffer)
        from .gloss_to_text import assemble_sentence_smart
        assembled = await assemble_sentence_smart(gloss_sequence)
        return RecognitionResult(
            gloss_sequence=gloss_sequence,
            sentence_text=assembled["sentence_text"],
            confidence=None,  # wire up real confidence once _run_inference exists
            status="ok",
        )

    def _run_inference(self, frames: List[LandmarkFrame]) -> List[str]:
        """
        Not implemented — this is where the trained model runs. Left as a
        clear failure point rather than a silent no-op, so it's obvious in
        testing that this needs the real model before Pipeline B can work
        end to end.
        """
        raise NotImplementedError(
            "SignRecognizer._run_inference: no trained model wired up yet."
        )
