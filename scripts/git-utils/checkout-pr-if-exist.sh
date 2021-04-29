#!/bin/bash
set -e
# get all opened PRs with specified label
RESULT=`curl -s https://api.github.com/search/issues?q=is:pr%20state:open%20label:$1%20repo:bio-tools/content`
# check if PR is created by github-actions bot and return pull request-number
PR_NUMBER=`jq '.items[]|select(.user.login == "github-actions[bot]")|.number' <<< $RESULT`
# get the branch name and remove quotes
TARGET_BRANCHNAME=`jq '.head.ref' <<< $(curl -s curl -s https://api.github.com/repos/bio-tools/content/pulls/$PR_NUMBER) | sed -r 's/^"|"$//g'`
echo "PR number: $PR_NUMBER"
echo "branch name: $TARGET_BRANCHNAME"

# check if $TARGET_BRANCHNAME is defined
if [ ! -z $TARGET_BRANCHNAME ]; then
    git fetch
    git checkout $TARGET_BRANCHNAME
    git status
    exit 0
else
  exit 1
fi
