#!/usr/bin/env bash
# Publish radar.json as the only file of the "radar" branch, replacing it each time (no history piles up: the live
# loop writes a new radar every couple of minutes). usage: radar_publish.sh path/to/radar.json "message"
set -euo pipefail
f="$1"; msg="${2:-Radar}"
export GIT_AUTHOR_NAME="First Flakes bot" GIT_AUTHOR_EMAIL="bot@users.noreply.github.com"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
blob=$(git hash-object -w "$f")
tree=$(printf "100644 blob %s\tradar.json\n" "$blob" | git mktree)
commit=$(git commit-tree "$tree" -m "$msg")
for i in 1 2 3; do git push -q -f origin "$commit:refs/heads/radar" && exit 0; sleep 3; done
exit 1
