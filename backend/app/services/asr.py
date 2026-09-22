# ASR (speech-to-text) is NOT done in this backend.
#
# Pipeline A's speech input runs entirely client-side through the browser's
# Web Speech API (see the architecture discussion) — the frontend sends
# already-recognized text to POST /translate/forward, so this backend never
# receives raw audio.
#
# This file is kept as a placeholder in case a future requirement needs
# server-side ASR (e.g. a kiosk without browser speech support), not
# because one is currently planned.
