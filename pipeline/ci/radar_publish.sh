#!/usr/bin/env bash
# Publish radar.json (and future.json, the forecast radar, when it is beside it) as the only files of the "radar"
# branch, replacing them each time (no history piles up: the live loop writes a new radar every couple of minutes).
# usage: radar_publish.sh path/to/radar.json "message"
set -euo pipefail
f="$1"; msg="${2:-Radar}"
export GIT_AUTHOR_NAME="First Flakes bot" GIT_AUTHOR_EMAIL="bot@users.noreply.github.com"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
entries=$(printf "100644 blob %s\tradar.json\n" "$(git hash-object -w "$f")")
fut="$(dirname "$f")/future.json"
if [ -f "$fut" ]; then entries="$entries"$'\n'$(printf "100644 blob %s\tfuture.json" "$(git hash-object -w "$fut")"); fi
tree=$(printf "%s\n" "$entries" | git mktree)
commit=$(git commit-tree "$tree" -m "$msg")
for i in 1 2 3; do git push -q -f origin "$commit:refs/heads/radar" && exit 0; sleep 3; done
exit 1
