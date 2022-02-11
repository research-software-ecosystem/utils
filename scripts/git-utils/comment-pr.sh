#!/bin/bash
# looking for the Pull Request by the label ($1) and put the comment on it ($2)

for i in {1..10}
do
    RESULT="$(curl -s https://api.github.com/search/issues?q=is:pr%20state:open%20label:$1%20repo:bio-tools/content)"
    COMMENTS_URL="$(jq -r '.items[]|select(.user.login == "github-actions[bot]")|.pull_request.url' <<< "$RESULT")"
    if [ ! -z "$COMMENTS_URL" ]; then
	    curl -s -u "$GITHUB_USER":"$GITHUB_TOKEN" -H 'Content-Type: application/json' -L "$COMMENTS_URL" -d '{"body": "'"$2"'"}'
        break
    fi
    sleep $(( i * i ))   # wait for pull request to be visualized
done
