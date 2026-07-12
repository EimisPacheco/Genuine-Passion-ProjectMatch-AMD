#!/usr/bin/env bash
# Rebuild the pitch deck PDF from docs/pitch-deck.html.
# Chrome emits one stray fragment page when paginating the slide grids, so we
# print, then drop any page with no text.
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=/tmp/deck-raw.pdf "file://$PWD/pitch-deck.html"
python3 - <<'PY'
from pypdf import PdfReader, PdfWriter
r, w = PdfReader("/tmp/deck-raw.pdf"), PdfWriter()
for page in r.pages:
    if (page.extract_text() or "").strip():
        w.add_page(page)
with open("Multi-Agent-Passion-Intelligence-AMD-Track3.pdf", "wb") as f:
    w.write(f)
print(f"rebuilt: {len(w.pages)} pages")
PY
