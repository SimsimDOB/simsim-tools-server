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
    number=$(echo "$pr_data" | jq -r .number)
    # Wait for CI. A PR with no checks makes `gh pr checks` fail, which is fine here.
    if ! gh pr checks "$number" --watch --fail-fast; then
        checks=$(gh pr checks "$number" 2>&1) || true
        [[ "$checks" == *"no checks reported"* ]] || exit 1
    fi
    # Squash so the PR title becomes the commit on main. No --delete-branch: it
    # checks out main locally, which fails while the root repo has main checked out.
    gh pr merge "$number" --squash
    git push origin --delete "$branch"
    echo "Merged. Clean up with: just rm <repo> $branch"
