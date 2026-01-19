#!/bin/bash
set +e

# Capture output to a file while streaming it to stdout
zero-infra-mod-registry "$@" 2>&1 | tee /tmp/result.txt
EXIT_CODE=${PIPESTATUS[0]}

# Read the result
RESULT=$(cat /tmp/result.txt)

# Set GitHub action outputs
if [ -n "$GITHUB_OUTPUT" ]; then
  # Set up GitHub step output with delimiter for multiline output
  echo "result<<EOF" >> $GITHUB_OUTPUT
  echo "$RESULT" >> $GITHUB_OUTPUT
  echo "EOF" >> $GITHUB_OUTPUT
  
  # Set failed status based on exit code
  if [ $EXIT_CODE -ne 0 ]; then
    echo "failed=true" >> $GITHUB_OUTPUT
    # Add to GitHub step summary if available
    if [ -n "$GITHUB_STEP_SUMMARY" ]; then
      echo ":x: Failed." >> $GITHUB_STEP_SUMMARY
      echo "" >> $GITHUB_STEP_SUMMARY
      echo '```' >> $GITHUB_STEP_SUMMARY
      echo "$RESULT" >> $GITHUB_STEP_SUMMARY
      echo '```' >> $GITHUB_STEP_SUMMARY
    fi
  else
    echo "failed=false" >> $GITHUB_OUTPUT
    # Add to GitHub step summary if available
    if [ -n "$GITHUB_STEP_SUMMARY" ]; then
      echo ":white_check_mark: All checks passed." >> $GITHUB_STEP_SUMMARY
      echo "" >> $GITHUB_STEP_SUMMARY
      echo '```' >> $GITHUB_STEP_SUMMARY
      echo "$RESULT" >> $GITHUB_STEP_SUMMARY
      echo '```' >> $GITHUB_STEP_SUMMARY
    fi
  fi
fi

# Exit with the same exit code as the main script
exit $EXIT_CODE
