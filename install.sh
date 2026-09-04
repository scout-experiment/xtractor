#!/usr/bin/env bash
# One-command installer for xtractor.
# Default: download the prebuilt xtractor.pyz from the latest GitHub release
# (no venv, no git needed; requires `gh`). `--from-source` keeps the classic
# venv + pip build from this clone and falls back to it automatically when
# the prebuilt download is unavailable.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10
REPO="scout-experiment/xtractor"
BIN_DIR="${HOME}/.local/bin"
LINK="${BIN_DIR}/xtractor"

fail() {
    printf 'install.sh: error: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: install.sh [--from-source] [SKILL_DIR]

Default: download the prebuilt xtractor.pyz from the latest GitHub release
(requires gh) and install it to ${LINK}. No venv, no git. Falls back to a
source build automatically if the download is unavailable.

  --from-source   build in ./.venv via pip instead of downloading the release
  SKILL_DIR       skill destination (default: \$XTRACTOR_SKILL_DIR or
                  ~/.agents/skills); skill copied to SKILL_DIR/xtractor/SKILL.md
  -h, --help      show this help
EOF
}

# --- Argument parsing --------------------------------------------------------

FROM_SOURCE=0
SKILL_DIR=""
for arg in "$@"; do
    case "$arg" in
        --from-source) FROM_SOURCE=1 ;;
        -h|--help) usage; exit 0 ;;
        --*) fail "unknown option: $arg (see --help)." ;;
        *)
            if [ -n "$SKILL_DIR" ]; then
                fail "unexpected extra argument: $arg (see --help)."
            fi
            SKILL_DIR="$arg"
            ;;
    esac
done
SKILL_DIR="${SKILL_DIR:-${XTRACTOR_SKILL_DIR:-${HOME}/.agents/skills}}"

# --- Prerequisite checks -----------------------------------------------------

require_python() {
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
}

# --- Shared steps -------------------------------------------------------------

install_skill() {
    mkdir -p "${SKILL_DIR}/xtractor" || fail "cannot create skill directory ${SKILL_DIR}/xtractor."
    cp skill/SKILL.md "${SKILL_DIR}/xtractor/SKILL.md" || fail "failed to copy skill/SKILL.md."
}

check_path() {
    case ":${PATH}:" in
        *":${BIN_DIR}:"*) : ;;
        *)
            printf '  warning: %s is not on PATH; add ~/.local/bin to PATH.\n' "${BIN_DIR}" >&2
            ;;
    esac
}

# --- Prebuilt release path ----------------------------------------------------

# Returns nonzero to signal fallback to the source build (except for hard
# failures, which call fail() and exit).
install_prebuilt() {
    if ! command -v gh >/dev/null 2>&1; then
        printf 'install.sh: prebuilt download skipped (gh not found); falling back to source build.\n' >&2
        return 1
    fi

    local tmpdir tmp
    tmpdir="$(mktemp -d)" || {
        printf 'install.sh: prebuilt download skipped (mktemp failed); falling back to source build.\n' >&2
        return 1
    }
    tmp="${tmpdir}/xtractor.pyz"
    # Fresh empty temp dir, so no --clobber needed. (--output is not
    # supported by every gh build; --dir + pattern lands exactly one file.)
    if ! gh release download --repo "$REPO" --pattern xtractor.pyz --dir "$tmpdir"; then
        rm -rf "$tmpdir"
        printf 'install.sh: prebuilt download failed (gh release download); falling back to source build.\n' >&2
        return 1
    fi

    if [ ! -s "$tmp" ] || [ "$(head -c 2 "$tmp")" != "#!" ]; then
        rm -rf "$tmpdir"
        printf 'install.sh: downloaded xtractor.pyz is empty or not a script; falling back to source build.\n' >&2
        return 1
    fi

    if [ -d "$LINK" ]; then
        rm -rf "$tmpdir"
        fail "${LINK} is a directory; remove it and re-run."
    fi
    if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
        printf 'install.sh: warning: replacing existing %s with the prebuilt release binary.\n' "$LINK" >&2
    fi

    chmod +x "$tmp"
    mv -f "$tmp" "$LINK"
    rm -rf "$tmpdir"

    # Sanity check: no args must be rejected with exit code 2.
    # Never runs an authenticated command; the CLI rejects before any backend.
    set +e
    "$LINK" </dev/null >/dev/null 2>&1
    SANITY_RC=$?
    set -e
    if [ "$SANITY_RC" -ne 2 ]; then
        rm -f "$LINK"
        printf 'install.sh: warning: prebuilt binary sanity check failed (exit %s, expected 2); falling back to source build.\n' "$SANITY_RC" >&2
        return 1
    fi
}

prebuilt_summary() {
    printf 'Installed xtractor (prebuilt release).\n'
    printf '  install source: prebuilt release\n'
    printf '  binary:         %s\n' "$LINK"
    printf '  skill:          %s\n' "${SKILL_DIR}/xtractor/SKILL.md"
    check_path
    printf 'Next step: xtractor status --yaml\n'
}

# --- Source build path --------------------------------------------------------

install_from_source() {
    if ! command -v git >/dev/null 2>&1; then
        fail "git not found. It is required to pull the pinned twitter-cli dependency from GitHub."
    fi

    if [ ! -d .venv ]; then
        python3 -m venv .venv || fail "failed to create .venv with python3 ${PY_VERSION}."
    fi

    if [ ! -x .venv/bin/python ]; then
        fail ".venv exists but .venv/bin/python is missing or not executable; remove .venv and re-run."
    fi

    .venv/bin/python -m pip install --force-reinstall . || \
        fail "pip install failed."

    # dist/xtractor.pyz, if present, is intentionally not linked: the venv script wins.
    if [ -d "${LINK}" ]; then
        fail "${LINK} is a directory; remove it and re-run."
    fi
    if [ -e "${LINK}" ] && [ ! -L "${LINK}" ]; then
        printf 'install.sh: warning: replacing existing %s with the .venv console script symlink.\n' "${LINK}" >&2
    fi
    ln -sfn "$(pwd)/.venv/bin/xtractor" "${LINK}" || fail "failed to create symlink ${LINK}."

    printf 'Installed xtractor (built from source).\n'
    printf '  install source: built from source\n'
    printf '  venv:           %s\n' "$(pwd)/.venv"
    printf '  console script: %s\n' "$(pwd)/.venv/bin/xtractor"
    printf '  skill:          %s\n' "${SKILL_DIR}/xtractor/SKILL.md"
    printf '  PATH symlink:   %s -> %s\n' "${LINK}" "$(pwd)/.venv/bin/xtractor"
    check_path
    printf 'Next step: xtractor status --yaml\n'
}

# --- Main ---------------------------------------------------------------------

require_python

if [ "$FROM_SOURCE" -eq 0 ]; then
    if install_prebuilt; then
        install_skill
        prebuilt_summary
        exit 0
    fi
    printf 'install.sh: continuing with source build.\n' >&2
fi

install_from_source
install_skill
