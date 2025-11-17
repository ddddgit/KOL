#!/usr/bin/env bash
#
# git-upload.sh
# One-shot: add all files, commit, and push to remote.

set -e

git config user.name "ddddgit"
# Use first argument as commit message, or fallback to auto message with timestamp
COMMIT_MSG="${1:-Auto-commit: $(date '+%Y-%m-%d %H:%M:%S')}"

# Make sure we are inside a git repo
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: this is not a git repository."
  exit 1
fi

# Show current branch
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Current branch: $BRANCH"

# Stage all changes (new, modified, deleted)
git add -A

# If nothing to commit, stop here
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

# Commit
echo "Committing with message: $COMMIT_MSG"
git commit -m "$COMMIT_MSG"

# Try to push to the upstream; if none set, push and set upstream to origin/BRANCH
if git rev-parse --abbrev-ref "@{u}" >/dev/null 2>&1; then
  echo "Pushing to existing upstream..."
  git push
else
  echo "No upstream set. Pushing to origin/$BRANCH and setting upstream..."
  git push -u origin "$BRANCH"
fi

echo "Done."

