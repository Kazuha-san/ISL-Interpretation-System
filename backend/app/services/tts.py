# TTS (text-to-speech) is NOT done in this backend, for the same reason as
# asr.py: Pipeline B's spoken output uses the browser's speech synthesis
# API client-side, driven by recognition_sessions.sentence_text once the
# signer confirms it (see app/routers/recognize.py).
#
# Kept as a placeholder in case server-side TTS (e.g. a non-browser kiosk
# display) becomes a real requirement later.
