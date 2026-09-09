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
      # Wrapping the value in an array keeps "absent" distinguishable from
      # "present but null" -- `.field // empty` renders both as the empty
      # string, so a field being added or removed would go unnoticed.
      old_val=$(jq -c --arg f "$field" 'if has($f) then [.[$f]] else "absent" end' old.json)
      new_val=$(jq -c --arg f "$field" 'if has($f) then [.[$f]] else "absent" end' new.json)
      [ "$old_val" = "$new_val" ] && continue

      # collectionID is append-only rather than frozen: an importer may add its
      # own collection -- bc2bt adds "BioConductor" by design, which is a real
      # change on 212 of the entries it updates -- but nothing may drop a
      # collection an entry already carries.
      if [ "$field" = "collectionID" ]; then
        removed=$(jq -rn --slurpfile a old.json --slurpfile b new.json \
          '(($a[0].collectionID // []) - ($b[0].collectionID // [])) | join(", ")')
        if [ -n "$removed" ]; then
          echo "::error file=$file::collectionID entries removed: $removed"
          failed=true
        fi
        continue
      fi

      echo "::error file=$file::Protected field '$field' was modified (old: $old_val, new: $new_val)"
      failed=true
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
