#!/usr/bin/env bash
# Post a validation report as a GitHub issue (create, or comment on the open
# one with the same title). Used by the <source>-validate composite actions.
#
#   report_issue.sh <source> <target-repo> <report-file>
#
# Requires: gh (present on GitHub runners), GH_TOKEN with issues:write on
# <target-repo>. The run link comes from GITHUB_SERVER_URL/GITHUB_REPOSITORY/
# GITHUB_RUN_ID when set.
set -euo pipefail

SOURCE="$1"
REPO="$2"
REPORT_FILE="$3"

TITLE="Validation report: ${SOURCE} imports"
BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

SUMMARY="$(tail -n 1 "$REPORT_FILE")"
RUN_LINK=""
if [ -n "${GITHUB_RUN_ID:-}" ]; then
    RUN_LINK="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID}"
fi

{
    echo "**${SUMMARY}**"
    echo
    [ -n "$RUN_LINK" ] && echo "Run: ${RUN_LINK}" && echo
    echo '```'
    # GitHub caps issue bodies at 65536 characters; keep headroom.
    head -c 60000 "$REPORT_FILE"
    if [ "$(wc -c < "$REPORT_FILE")" -gt 60000 ]; then
        echo
        echo "... (truncated; see the full log in the workflow run)"
    fi
    echo '```'
} > "$BODY_FILE"

# Comment on the open issue with this exact title, if any; else create it.
EXISTING="$(gh issue list --repo "$REPO" --state open \
    --search "in:title \"$TITLE\"" \
    --json number,title \
    --jq ".[] | select(.title == \"$TITLE\") | .number" | head -n 1)"

if [ -n "$EXISTING" ]; then
    gh issue comment "$EXISTING" --repo "$REPO" --body-file "$BODY_FILE"
    echo "commented on ${REPO}#${EXISTING}"
else
    gh issue create --repo "$REPO" --title "$TITLE" --body-file "$BODY_FILE"
fi
