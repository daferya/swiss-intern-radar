#!/usr/bin/env bash
# One-time setup with the GitHub CLI (https://cli.github.com).
# Creates a public repository, pushes this folder, switches GitHub Pages to "GitHub Actions"
# and starts the first run.   Usage:  bash scripts/setup_github.sh [repo-name]
set -euo pipefail

NAME="${1:-swiss-intern-radar}"
command -v gh >/dev/null || { echo "Install the GitHub CLI first: https://cli.github.com"; exit 1; }
gh auth status >/dev/null 2>&1 || gh auth login

cd "$(dirname "$0")/.."
if [ ! -d .git ]; then
  git init -q -b main
  git add -A
  git commit -qm "Swiss AI internship radar"
fi

gh repo create "$NAME" --public --source=. --remote=origin --push
OWNER="$(gh api user -q .login)"
REPO="$OWNER/$NAME"
OWNER_LC="$(printf '%s' "$OWNER" | tr '[:upper:]' '[:lower:]')"

# Publish the website from the workflow (Settings > Pages > Source: GitHub Actions)
gh api -X POST "repos/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$REPO/pages" -f build_type=workflow >/dev/null

# Show the repository link in the website footer
sed -i.bak "s#^  repo_url: \"\".*#  repo_url: \"https://github.com/$REPO\"#" config.yaml && rm -f config.yaml.bak
git commit -qam "Set repository URL" && git push -q

gh workflow run radar.yml
echo
echo "First run started:   https://github.com/$REPO/actions"
echo "Your radar (in ~5 min): https://$OWNER_LC.github.io/$NAME/"
