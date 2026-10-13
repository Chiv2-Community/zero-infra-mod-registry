#!/usr/bin/env bash
set -euo pipefail
image=${1:?Pass the built registry image}
temp=$(mktemp -d)
trap 'rm -rf "$temp"' EXIT
mkdir -p "$temp/registry" "$temp/package_db/packages" "$temp/dll_db"
touch "$temp/output"
run_action() {
  docker run --rm --user "$(id -u):$(id -g)" \
    --env GITHUB_TOKEN=offline-validation --env VERIFY_DLL_DOWNLOADS=true \
    --env GITHUB_OUTPUT=/github/workspace/output \
    --volume "$temp:/github/workspace" --workdir /github/workspace \
    "$image" validate '' ''
}
run_action
grep -qx 'failed=false' "$temp/output"
grep -q '^result<<' "$temp/output"
printf 'Missing/Package\n' > "$temp/package_db/mod_list_index.txt"
: > "$temp/output"
if run_action; then echo 'Invalid registry returned success' >&2; exit 1; fi
grep -qx 'failed=true' "$temp/output"
echo 'registry Docker action tests passed'
