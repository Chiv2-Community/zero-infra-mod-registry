#!/usr/bin/env bash
set -euo pipefail
git check-ref-format "refs/heads/$SOURCE_BRANCH"
git check-ref-format "refs/heads/$TARGET_BRANCH"
[[ "$SOURCE_BRANCH" != "$TARGET_BRANCH" ]]
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$GITHUB_REF" == "refs/heads/$SOURCE_BRANCH" ]]
[[ $(git rev-parse HEAD) == "$SOURCE_SHA" ]]
git fetch --no-tags origin "+refs/heads/$SOURCE_BRANCH:refs/remotes/origin/$SOURCE_BRANCH"
git cat-file -e "$SOURCE_SHA^{commit}"
git merge-base --is-ancestor "$SOURCE_SHA" "refs/remotes/origin/$SOURCE_BRANCH"
git fetch --no-tags origin "refs/heads/$TARGET_BRANCH:refs/remotes/origin/$TARGET_BRANCH"
git checkout --detach "refs/remotes/origin/$TARGET_BRANCH"
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
if git merge-base --is-ancestor "$SOURCE_SHA" HEAD; then
  echo 'Destination already contains the source snapshot.'
elif ! git merge --no-edit "$SOURCE_SHA"; then
  git merge --abort
  echo 'Merge conflicted; destination was not pushed.' >&2
  exit 1
fi
echo "candidate_sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"
