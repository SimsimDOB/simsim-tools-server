run:
    poetry run main

deploy:
    gh pr merge --merge $(gh pr list --label "autorelease: pending" --json number --jq '.[0].number')
