#!/usr/bin/env bash
set -euo pipefail
git check-ref-format "refs/heads/$TARGET_BRANCH"
[[ "$CANDIDATE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ $(git rev-parse HEAD) == "$CANDIDATE_SHA" ]]
git push origin "$CANDIDATE_SHA:refs/heads/$TARGET_BRANCH"
