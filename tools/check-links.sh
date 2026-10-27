#!/bin/sh
# Verifies all external links and reports unreachable targets.
#
#     tools/check-links.sh             checks dist/
#     tools/check-links.sh DIRECTORY   checks another output directory
#
set -eu
ROOT_DIR=$(dirname "$0")/..
SITE=${1:-"$ROOT_DIR/dist"}
ls "$SITE"/*.html >/dev/null 2>&1 || {
  echo "ERROR: no HTML pages in $SITE; run tools/build.sh first." >&2
  exit 2
}
OWN_DOMAIN=$(tr -d '[:space:]' < "$ROOT_DIR/public/CNAME")

TEMP_LIST=$(mktemp)
trap 'rm -f "$TEMP_LIST"' EXIT HUP INT TERM

python3 - "$OWN_DOMAIN" "$SITE"/*.html > "$TEMP_LIST" <<'PY' || { echo "ERROR: failed parsing links." >&2; exit 2; }
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

own = {sys.argv[1], "www." + sys.argv[1]}
found = set()


class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                url = urlsplit(value.strip())
                if url.scheme in ("http", "https") and url.hostname not in own:
                    found.add(value.strip())


for name in sys.argv[2:]:
    parser = Links(convert_charrefs=True)
    parser.feed(Path(name).read_text(encoding="utf-8"))
    parser.close()
for address in sorted(found):
    print(address)
PY
echo "External addresses found: $(wc -l < "$TEMP_LIST")" >&2

RESULT=0
while read -r url; do
  exit_code=0
  status=$(curl -sSL --max-time 30 --retry 2 --retry-delay 5 \
    -o /dev/null -w '%{http_code}' \
    -A 'aimergentia.com Link Verification (+https://aimergentia.com/)' \
    "$url" 2>/dev/null) || exit_code=$?
  [ "$exit_code" -eq 0 ] || status="${status:-000}, request aborted (curl $exit_code)"
  printf '  %s  %s\n' "$status" "$url" >&2
  case "$status" in
    2??|3??) ;;
    *)
      printf -- '- `%s` -> HTTP %s\n' "$url" "$status"
      RESULT=1 ;;
  esac
done < "$TEMP_LIST"
exit "$RESULT"

