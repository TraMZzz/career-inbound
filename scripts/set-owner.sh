#!/usr/bin/env bash
# Replace the GitHub owner placeholder in all tracked files: scripts/set-owner.sh <github-user-or-org>
set -euo pipefail
owner="${1:?usage: scripts/set-owner.sh <github-user-or-org>}"
cd "$(git rev-parse --show-toplevel)"
files=$(git grep -l '<ORG>' -- . ':!scripts/set-owner.sh' || true)
[ -z "$files" ] && { echo "nothing to replace"; exit 0; }
for f in $files; do sed -i.bak "s#<ORG>#${owner}#g" "$f" && rm "$f.bak"; done
echo "$files" | sed 's/^/updated: /'
