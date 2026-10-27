#!/bin/sh
# Automated validation suite for Aimergentia: build, link integrity, security headers, and contrast.
set -eu
[ "$#" -eq 0 ] || { echo "ERROR: unknown argument $1" >&2; exit 2; }
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT HUP INT TERM
AIMERGENTIA_TEST_SITE="$WORK_DIR/site"
export AIMERGENTIA_TEST_SITE
python3 tools/build.py --output "$AIMERGENTIA_TEST_SITE"
python3 -m unittest discover -s tests
echo 'Verified: build, links, security headers, and contrast.'
