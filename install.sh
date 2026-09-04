#!/usr/bin/env bash
# One-command installer for xtractor: venv setup, dependency install, and skill placement.
set -euo pipefail

PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

fail() {
    printf 'install.sh: error: %s\n' "$1" >&2
    exit 1
}

# --- Prerequisite checks ---------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found. Install Python >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} and re-run."
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')" || \
    fail "could not determine python3 version."

PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [ "$PY_MAJOR" -lt "$PYTHON_MIN_MAJOR" ] || \
   { [ "$PY_MAJOR" -eq "$PYTHON_MIN_MAJOR" ] && [ "$PY_MINOR" -lt "$PYTHON_MIN_MINOR" ]; }; then
    fail "python3 >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} required, found ${PY_VERSION}."
fi

if ! command -v git >/dev/null 2>&1; then
    fail "git not found. It is required to pull the pinned twitter-cli dependency from GitHub."
fi

# --- Virtual environment + install -----------------------------------------

if [ ! -d .venv ]; then
    python3 -m venv .venv || fail "failed to create .venv with python3 ${PY_VERSION}."
fi

if [ ! -x .venv/bin/python ]; then
    fail ".venv exists but .venv/bin/python is missing or not executable; remove .venv and re-run."
fi

.venv/bin/python -m pip install --force-reinstall . || \
    fail "pip install failed."

# --- Skill placement --------------------------------------------------------

SKILL_DIR="${1:-${XTRACTOR_SKILL_DIR:-${HOME}/.agents/skills}}"
mkdir -p "${SKILL_DIR}/xtractor" || fail "cannot create skill directory ${SKILL_DIR}/xtractor."
cp skill/SKILL.md "${SKILL_DIR}/xtractor/SKILL.md" || fail "failed to copy skill/SKILL.md."


# --- PATH exposure ----------------------------------------------------------

BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}" || fail "cannot create ${BIN_DIR}."
LINK="${BIN_DIR}/xtractor"
# dist/xtractor.pyz, if present, is intentionally not linked: the venv script wins.
if [ -e "${LINK}" ] && [ ! -L "${LINK}" ]; then
    printf 'install.sh: warning: %s exists and is not a symlink; leaving it untouched.\n' "${LINK}" >&2
else
    ln -sfn "$(pwd)/.venv/bin/xtractor" "${LINK}" || fail "failed to create symlink ${LINK}."
fi


printf 'Installed xtractor.\n'
printf '  venv:           %s\n' "$(pwd)/.venv"
printf '  console script: %s\n' "$(pwd)/.venv/bin/xtractor"
printf '  skill:          %s\n' "${SKILL_DIR}/xtractor/SKILL.md"
printf '  PATH symlink:   %s -> %s\n' "${LINK}" "$(pwd)/.venv/bin/xtractor"
case ":${PATH}:" in
    *":${BIN_DIR}:"*) : ;;
    *)
        printf '  warning: %s is not on PATH; add ~/.local/bin to PATH.\n' "${BIN_DIR}" >&2
        ;;
esac
printf 'Next step: xtractor status --yaml\n'
