#!/bin/sh
# Configures git pre-commit hooks for the repository.
#
#     tools/setup.sh
#
set -eu
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath tools/hooks
echo "  Pre-commit hooks configured: $(git config core.hooksPath)"
echo "  To disable: git config --unset core.hooksPath"

