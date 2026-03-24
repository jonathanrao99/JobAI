#!/usr/bin/env bash
# Next dev sometimes leaves a corrupted .next (ENOENT app-build-manifest / _buildManifest.js.tmp).
# Run this, then start npm run dev again.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf "$ROOT/frontend/.next"
echo "Removed $ROOT/frontend/.next — restart with: npm run dev"
