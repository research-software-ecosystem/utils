#!/bin/bash
set -e

# Validate protected fields in biotools.json files
# Usage: ./validate-biotools-fields.sh <file1> [file2] [file3] ...
# Environment: GITHUB_BEFORE_SHA - the commit SHA to compare against

PROTECTED_FIELDS=(
  "biotoolsID"
  "biotoolsCURIE"
  "additionDate"
  "collectionID"
  "elixirPlatform"
  "elixirNode"
  "elixirCommunity"
  "lastUpdate"
  "owner"
  "editPermission"
  "validated"
  "homepage_status"
  "elixir_badge"
  "confidence_flag"
)

failed=false

for file in "$@"; do
  echo "Validating $file..."
  
  # Check if this is a new file or existing file
  if ! git show "${GITHUB_BEFORE_SHA}:${file}" > old.json 2>/dev/null; then
    # NEW FILE
    echo "ℹ New file detected: $file"
    echo "ℹ Skipping validation for protected fields..."
  else
    # EXISTING FILE
    echo "ℹ Existing file: $file"
    cat "$file" > new.json
    
    for field in "${PROTECTED_FIELDS[@]}"; do
      old_val=$(jq -r ".$field // empty" old.json 2>/dev/null)
      new_val=$(jq -r ".$field // empty" new.json 2>/dev/null)
      if [ "$old_val" != "$new_val" ]; then
        echo "::error file=$file::Protected field '$field' was modified (old: '$old_val', new: '$new_val')"
        failed=true
      fi
    done
    
    rm -f old.json new.json
  fi
done

if [ "$failed" = true ]; then
  echo "::error::Validation failed - protected fields were modified."
  exit 1
else
  echo "✅ All validation checks passed"
fi
