#!/usr/bin/env bash
# Local CI simulation — mirrors .github/workflows/ci.yml
#
# Usage:
#   bash ci-local.sh          — full CI (lock + lint + tests + docs + package)
#   bash ci-local.sh --fast   — fast checks only (lock + lint), for pre-commit

set -euo pipefail

FAST=false
[[ "${1:-}" == "--fast" ]] && FAST=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
step() { echo -e "\n${YELLOW}==>${NC} $*"; }

cd "$(git rev-parse --show-toplevel)"

# ── 0. Lock file ──────────────────────────────────────────────────────────────
#
# The analogue of a generated file left out of date: silent here, fatal in CI,
# where every job runs `uv run --frozen` and refuses to resolve.
step "Checking uv.lock matches pyproject.toml"
if ! uv lock --check >/dev/null 2>&1; then
  echo ""
  echo "Run 'uv lock', re-stage uv.lock, and commit."
  fail "Lock file out of date"
fi
ok "Lock file"

# ── 1. Lint ───────────────────────────────────────────────────────────────────
step "Checking lint (ruff)"
if ! uv run --frozen ruff check .; then
  echo ""
  echo "Run 'uv run ruff check --fix .', re-stage, and commit."
  fail "Lint check failed"
fi
ok "Lint"

# ── 2. Formatting ─────────────────────────────────────────────────────────────
step "Checking formatting (ruff)"
if ! uv run --frozen ruff format --check .; then
  echo ""
  echo "Run 'uv run ruff format .', re-stage, and commit."
  fail "Formatting check failed"
fi
ok "Formatting"

if $FAST; then
  echo -e "\n${GREEN}Fast checks passed — safe to commit.${NC}"
  exit 0
fi

# ── 3. Tests ──────────────────────────────────────────────────────────────────
#
# CITEKEEP_NETWORK_TESTS stays unset, as in CI: a suite that goes red because
# zbMATH is slow teaches nothing. Run those by hand when a source adapter
# changes.
step "Running tests (pytest)"
uv run --frozen pytest -q || fail "Tests failed"
ok "Tests"

# ── 4. Documentation ──────────────────────────────────────────────────────────
#
# --strict turns warnings into failures: a docstring documenting a parameter
# with no type annotation, a nav entry pointing at a missing page, a dead
# internal link. Read the Docs fails on warnings too, so this is also the
# guarantee that the published site will build.
step "Building documentation (mkdocs --strict)"
if ! output=$(uv run --frozen --extra docs mkdocs build --strict 2>&1); then
  echo "$output"
  fail "Documentation build failed"
fi
ok "Documentation"

# ── 5. Package ────────────────────────────────────────────────────────────────
#
# Catches a README that PyPI would refuse to render, long before a version
# number is spent — a released version can never be re-uploaded.
step "Building and checking the distributions"
rm -rf dist
if ! output=$(uv build 2>&1); then echo "$output"; fail "Build failed"; fi
if ! output=$(uvx twine check --strict dist/* 2>&1); then
  echo "$output"
  fail "twine check failed"
fi
ok "Package"

echo -e "\n${GREEN}All checks passed — safe to push.${NC}"
