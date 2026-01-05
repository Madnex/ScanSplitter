#!/bin/bash
set -e

# Usage: ./scripts/release.sh [major|minor|patch]
# Default: patch

BUMP_TYPE="${1:-patch}"
PYPROJECT="pyproject.toml"

# Extract current version
CURRENT_VERSION=$(grep -E '^version = ' "$PYPROJECT" | sed 's/version = "\(.*\)"/\1/')

if [[ -z "$CURRENT_VERSION" ]]; then
    echo "Error: Could not find version in $PYPROJECT"
    exit 1
fi

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Bump version
case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
    *)
        echo "Usage: $0 [major|minor|patch]"
        exit 1
        ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"

echo "Bumping version: $CURRENT_VERSION → $NEW_VERSION"

# Update pyproject.toml
sed -i.bak "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"
rm -f "$PYPROJECT.bak"

# Git operations
git add "$PYPROJECT"
git commit -m "Bump version to $NEW_VERSION"
git tag "v$NEW_VERSION"

echo "Pushing commit and tag..."
git push
git push origin "v$NEW_VERSION"

echo ""
echo "Released v$NEW_VERSION"
