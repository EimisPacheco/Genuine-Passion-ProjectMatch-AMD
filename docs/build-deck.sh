#!/usr/bin/env bash
# Rebuild the pitch deck PDF from docs/pitch-deck.html.
# Chrome emits one stray fragment page when paginating the slide grids, so we
# print, then drop any page that has no text.
set -euo pipefail
cd "$(dirname "$0")/.."

# find a python that has pypdf; install it if none does
PY=""
for cand in python3 .venv311/bin/python3 .venv/bin/python3; do
  command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ] || continue
  if "$cand" -c "import pypdf" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  PY="python3"
  "$PY" -m pip install --quiet pypdf >/dev/null 2>&1 || \
  "$PY" -m pip install --quiet --break-system-packages pypdf >/dev/null 2>&1
fi

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=/tmp/deck-raw.pdf "file://$PWD/docs/pitch-deck.html" 2>/dev/null

"$PY" - <<'PY'
from pypdf import PdfReader, PdfWriter
r, w = PdfReader("/tmp/deck-raw.pdf"), PdfWriter()
dropped = [i for i, p in enumerate(r.pages, 1) if not (p.extract_text() or "").strip()]
for p in r.pages:
    if (p.extract_text() or "").strip():
        w.add_page(p)
out = "docs/Multi-Agent-Passion-Intelligence-AMD-Track3.pdf"
with open(out, "wb") as f:
    w.write(f)
print(f"rebuilt: {len(w.pages)} pages (dropped stray page {dropped or 'none'})")
PY
