#!/bin/sh
# Rendert die drei Bilddateien der Website aus ihren SVG-Quellen:
#
#     public/vorschau.png          1200x630, Open Graph — aus src/grafik/vorschau.svg
#     public/apple-touch-icon.png   180x180, iOS-Startbildschirm — aus src/grafik/signet.svg
#     public/favicon.ico             32x32, Browserleiste — aus src/grafik/signet.svg
#
#     tools/bilder-erzeugen.sh
#
# Braucht Chromium oder Chrome und python3. Die erzeugten Dateien sind
# versioniert, damit der normale Build keinen Browser braucht.
#
# Gerendert wird in ein Arbeitsverzeichnis. public/ wird erst angefasst, wenn
# alle drei Bilder vorliegen und ihre Maße stimmen — ein abgebrochener Export
# hinterlässt keinen halben Satz (R-QUELLE-1).
set -eu
cd "$(dirname "$0")/.."

# Der Browser heißt je nach System anders: unter Debian und Ubuntu chromium
# oder chromium-browser, auf den GitHub-Läufern google-chrome.
BROWSER=${BROWSER:-}
if [ -z "$BROWSER" ]; then
  for kandidat in chromium chromium-browser google-chrome google-chrome-stable chrome; do
    if command -v "$kandidat" >/dev/null 2>&1; then
      BROWSER=$kandidat
      break
    fi
  done
fi
[ -n "$BROWSER" ] || { echo "FEHLER: kein Chromium oder Chrome gefunden." >&2; exit 1; }

# Im Repository statt in /tmp: Ein als Snap installiertes Chromium darf dort
# nicht schreiben. Das Muster .build.*/ steht in .gitignore.
ARBEITSVERZEICHNIS=$(mktemp -d "$PWD/.build.bilder.XXXXXX")
trap 'rm -rf "$ARBEITSVERZEICHNIS"' EXIT HUP INT TERM

rendere() {
  # $1 Quelle, $2 Zieldatei im Arbeitsverzeichnis, $3 Breite, $4 Höhe
  "$BROWSER" --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=1 --window-size="$3,$4" \
    --screenshot="$ARBEITSVERZEICHNIS/$2" "file://$PWD/$1" 2>/dev/null \
    || { echo "FEHLER: $BROWSER konnte $1 nicht rendern." >&2; exit 1; }
}

rendere src/grafik/vorschau.svg vorschau.png         1200 630
rendere src/grafik/signet.svg   apple-touch-icon.png  180 180
rendere src/grafik/signet.svg   favicon-32.png         32  32

# Maße prüfen und das ICO bauen. ICO ist ein Behälter; seit Vista darf darin
# ein PNG stehen.
python3 - "$ARBEITSVERZEICHNIS" <<'PY'
import struct
import sys
from pathlib import Path

work = Path(sys.argv[1])
expected = {"vorschau.png": (1200, 630), "apple-touch-icon.png": (180, 180), "favicon-32.png": (32, 32)}
for name, size in expected.items():
    path = work / name
    data = path.read_bytes() if path.is_file() else b""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        sys.exit(f"FEHLER: {name} ist kein PNG; der Browser hat nichts Brauchbares geschrieben.")
    actual = struct.unpack(">II", data[16:24])
    if actual != size:
        sys.exit(f"FEHLER: {name} hat {actual[0]}x{actual[1]} statt {size[0]}x{size[1]} Pixel.")

daten = (work / "favicon-32.png").read_bytes()
kopf = struct.pack("<HHH", 0, 1, 1)
eintrag = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(daten), 6 + 16)
(work / "favicon.ico").write_bytes(kopf + eintrag + daten)
PY

for name in vorschau.png apple-touch-icon.png favicon.ico; do
  mv "$ARBEITSVERZEICHNIS/$name" "public/$name"
  echo "  public/$name  $(stat -c%s "public/$name") B"
done
