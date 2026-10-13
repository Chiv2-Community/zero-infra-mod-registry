#!/usr/bin/env bash
set -euo pipefail
script=$(realpath "$(dirname "$0")/../../actions/publish-branch/publish.sh")
push=$(realpath "$(dirname "$0")/../../actions/publish-branch/push.sh")
temp=$(mktemp -d)
trap 'rm -rf "$temp"' EXIT
git init --bare "$temp/remote.git" >/dev/null
git clone "$temp/remote.git" "$temp/work" >/dev/null 2>&1
cd "$temp/work"
export GITHUB_OUTPUT="$temp/output"
publish() {
  : > "$GITHUB_OUTPUT"
  bash "$script"
  CANDIDATE_SHA=$(sed -n 's/^candidate_sha=//p' "$GITHUB_OUTPUT")
  export CANDIDATE_SHA
  bash "$push"
}
git config user.name Test
git config user.email test@example.com
git checkout -b main
echo initial > registry.txt
git add registry.txt
git commit -m initial >/dev/null
git branch db
git push origin main db >/dev/null 2>&1
echo approved >> registry.txt
git commit -am approved >/dev/null
git push origin main >/dev/null 2>&1
SOURCE_SHA=$(git rev-parse HEAD)
export SOURCE_SHA SOURCE_BRANCH=main TARGET_BRANCH=db GITHUB_REF=refs/heads/main
publish
[[ $(git ls-remote origin refs/heads/db | cut -f1) == "$SOURCE_SHA" ]]
git checkout --detach "$SOURCE_SHA"
publish # repeated delivery does not write another commit
[[ $(git ls-remote origin refs/heads/db | cut -f1) == "$SOURCE_SHA" ]]
git checkout -b unapproved "$SOURCE_SHA"
echo unapproved >> registry.txt
git commit -am unapproved >/dev/null
SOURCE_SHA=$(git rev-parse HEAD)
if bash "$script"; then echo 'Unapproved source was accepted' >&2; exit 1; fi
[[ $(git ls-remote origin refs/heads/db | cut -f1) != "$SOURCE_SHA" ]]
SOURCE_SHA=$(git rev-parse origin/main)
export GITHUB_REF=refs/heads/other
git checkout --detach "$SOURCE_SHA"
if bash "$script"; then echo 'Wrong source branch accepted' >&2; exit 1; fi
export GITHUB_REF=refs/heads/main
# Divergent destination edits must fail without a force push.
git checkout -B db origin/db
echo conflicting > registry.txt
git commit -am conflicting >/dev/null
git push origin db >/dev/null 2>&1
destination=$(git rev-parse HEAD)
git checkout main
echo newer > registry.txt
git commit -am newer >/dev/null
git push origin main >/dev/null 2>&1
SOURCE_SHA=$(git rev-parse HEAD)
if bash "$script"; then echo 'Conflict was accepted' >&2; exit 1; fi
[[ $(git ls-remote origin refs/heads/db | cut -f1) == "$destination" ]]
# A changed HEAD must never publish a different tree than the validated candidate.
CANDIDATE_SHA=$SOURCE_SHA
if bash "$push"; then echo 'Changed candidate was accepted' >&2; exit 1; fi
# A destination advance after validation rejects the stale candidate, never forces.
CANDIDATE_SHA=$(git rev-parse HEAD)
git checkout -b racer
echo race > race.txt
git add race.txt
git commit -m race >/dev/null
git push origin HEAD:db >/dev/null 2>&1
raced=$(git rev-parse HEAD)
git checkout --detach "$CANDIDATE_SHA"
if bash "$push"; then echo 'Push race was accepted' >&2; exit 1; fi
[[ $(git ls-remote origin refs/heads/db | cut -f1) == "$raced" ]]
echo 'publish-branch tests passed'
