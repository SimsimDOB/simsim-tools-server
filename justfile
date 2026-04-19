run:
    poetry run main

deploy:
    gh pr merge --merge $(gh pr list --label "autorelease: pending" --json number --jq '.[0].number')

merge:
    #!/usr/bin/env bash
    set -euo pipefail
    branch=$(git branch --show-current)
    pr_data=$(gh pr view --json number,baseRefName 2>/dev/null) || { echo "No PR found for branch '$branch'"; exit 1; }
    base=$(echo "$pr_data" | jq -r '.baseRefName')
    gh pr merge --merge --delete-branch
    git checkout "$base"
    git pull
    git branch -d "$branch"
