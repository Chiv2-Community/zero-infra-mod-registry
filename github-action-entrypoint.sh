#!/bin/bash
set +e

# Capture output to a file while streaming it to stdout
# Docker actions supply empty optional repo/tag positional arguments. Omit them
# so commands such as validate (including DLL verification) receive only values.
ARGS=()
for ARG in "$@"; do
  if [[ -n "$ARG" ]]; then
    ARGS+=("$ARG")
  fi
done
# Match the checkout owner so later host-side Git steps can remove new files
# and directories. Standalone and already non-root containers keep their user.
python -c '
import os
import sys

workspace = os.environ.get("GITHUB_WORKSPACE")
if os.geteuid() == 0 and workspace:
    owner = os.stat(workspace)
    os.setgroups([])
    os.setgid(owner.st_gid)
    os.setuid(owner.st_uid)
os.execvp("zero-infra-mod-registry", ["zero-infra-mod-registry", *sys.argv[1:]])
' "${ARGS[@]}" 2>&1 | tee /tmp/result.txt
EXIT_CODE=${PIPESTATUS[0]}

# Read the result
RESULT=$(cat /tmp/result.txt)

# Set GitHub action outputs
if [ -n "$GITHUB_OUTPUT" ]; then
  # Set up GitHub step output with delimiter for multiline output
   # Use a more unique delimiter to avoid collisions
  DELIMITER=$(dd if=/dev/urandom bs=15 count=1 2>/dev/null | base64 | tr -dc 'a-zA-Z0-9')
  echo "result<<$DELIMITER" >> "$GITHUB_OUTPUT"
  echo "$RESULT" >> "$GITHUB_OUTPUT"
  echo "$DELIMITER" >> "$GITHUB_OUTPUT"
  
  # Set failed status based on exit code
  if [ $EXIT_CODE -ne 0 ]; then
    echo "failed=true" >> "$GITHUB_OUTPUT"
    # Add to GitHub step summary if available
    if [ -n "$GITHUB_STEP_SUMMARY" ]; then
      echo ":x: Failed." >> "$GITHUB_STEP_SUMMARY"
      echo "" >> "$GITHUB_STEP_SUMMARY"
      echo '```' >> "$GITHUB_STEP_SUMMARY"
      echo "$RESULT" >> "$GITHUB_STEP_SUMMARY"
      echo '```' >> "$GITHUB_STEP_SUMMARY"
    fi
  else
    echo "failed=false" >> "$GITHUB_OUTPUT"
    # Add to GitHub step summary if available
    if [ -n "$GITHUB_STEP_SUMMARY" ]; then
      echo ":white_check_mark: All checks passed." >> "$GITHUB_STEP_SUMMARY"
      echo "" >> "$GITHUB_STEP_SUMMARY"
      echo '```' >> "$GITHUB_STEP_SUMMARY"
      echo "$RESULT" >> "$GITHUB_STEP_SUMMARY"
      echo '```' >> "$GITHUB_STEP_SUMMARY"
    fi
  fi
fi

# Exit with the same exit code as the main script
exit $EXIT_CODE
