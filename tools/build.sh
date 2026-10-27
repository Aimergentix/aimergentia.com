#!/bin/sh
# Erzeugt dist/ aus src/ und public/. Von jedem Arbeitsverzeichnis aufrufbar.
set -eu
exec python3 -B "$(dirname "$0")/build.py" "$@"
