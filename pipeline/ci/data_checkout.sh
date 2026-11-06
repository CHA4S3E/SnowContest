#!/usr/bin/env bash
# Put the data branch in ./data (created from seed/ the first time).
set -euo pipefail
git config user.name "First Flakes bot"; git config user.email "bot@users.noreply.github.com"
if git ls-remote --exit-code --heads origin data >/dev/null 2>&1; then
  git fetch origin data
  git worktree add data origin/data -f --detach
  (cd data && git checkout -B data origin/data)
else
  git worktree add --orphan -b data data
fi
if [ ! -f data/config.json ]; then cp seed/*.json data/; fi
