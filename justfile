run:
    poetry run main

deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    gh pr create --base release --head main --title "Deploy" --body ""
    pr_number=$(gh pr view main --repo SimsimDOB/simsim-tools-server --json number --jq '.number')
    gh pr merge "$pr_number" --merge

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
