run:
    poetry run main

deploy:
    gh pr merge --merge $(gh pr list --label "autorelease: pending" --json number --jq '.[0].number')

merge:
    #!/usr/bin/env bash
    set -euo pipefail
    branch=$(git branch --show-current)
    pr_data=$(gh pr view --json number,baseRefName 2>/dev/null) || { echo "No PR found for branch '$branch'"; exit 1; }
    git fetch origin "$branch"
    local_sha=$(git rev-parse HEAD)
    remote_sha=$(git rev-parse "origin/$branch")
    if [ "$local_sha" != "$remote_sha" ]; then
        echo "Branch is not up to date, pulling..."
        git pull
    fi
    gh pr merge --merge --delete-branch --auto
    git pull
