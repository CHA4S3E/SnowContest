#!/usr/bin/env bash
set -euo pipefail
cd data
git config user.name "First Flakes bot"; git config user.email "bot@users.noreply.github.com"
git add -A
if git diff --cached --quiet; then echo "no data changes"; exit 0; fi
git commit -q -m "$1"
for i in 1 2 3 4; do
  if git push origin HEAD:data; then exit 0; fi
  git pull --rebase origin data || true
done
exit 1
