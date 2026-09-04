# Repository Guidelines

## Project Overview

Xtractor is a small Python CLI that exposes read-only Twitter/X operations. It validates commands and optional cookie input, then delegates retrieval to the installed `twitter-cli` backend.

## Architecture & Data Flow

`xtractor` maps to `xtractor_cli.cli:main` through `pyproject.toml`.

1. `main()` reads `argv` and rejects commands outside `READ_COMMANDS` with exit code `2`.
2. If `XTRACTOR_COOKIE_FILE` is set, or the default `~/.config/xtractor/cookies.json` exists, `_cookie_env()` validates the Cookie-Editor JSON file and extracts `auth_token` and `ct0`.
3. `_read_proxy()` reads the optional proxy from the JSON config file (`XTRACTOR_CONFIG` or `~/.config/xtractor/config.json`; only when `TWITTER_PROXY` is unset) and validates its scheme and shape.
4. The wrapper calls the project backend in-process (`xtractor_cli.backend.main()`), which resolves the live `UserTweets` queryId and delegates to the pinned `twitter-cli` CLI. This keeps the wrapper zipapp-safe (no sibling interpreter needed).
5. A missing backend dependency returns `127`. Validation errors fail before the backend call.

Keep this architecture synchronous, stateless, and thin. Put shared security checks at the wrapper boundary rather than in each command path.

## Key Directories

- `xtractor_cli/`: shipped Python package and CLI implementation.
- `tests/`: stdlib `unittest` behavioral tests.
- `skill/`: agent-facing usage, authentication, and failure policy.
- `.venv/`: generated local environment; do not edit or treat its scripts as source.

## Development Commands

Use Python 3.10 or newer and a virtual environment.
For a one-command setup, run `./install.sh`: it creates `.venv`, installs the package plus the git-pinned dependency, and copies the skill to `~/.agents/skills/xtractor/`. The manual commands below remain as the alternative.

```bash
python -m venv .venv
.venv/bin/python -m pip install --force-reinstall --no-deps .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q xtractor_cli tests
.venv/bin/xtractor status --yaml
```

The console script runs code from the installed wheel. Reinstall after each `xtractor_cli/` source change before CLI smoke tests.

Build support comes from Hatchling. If the `build` package is installed, create distributions with `python -m build`.

## Code Conventions & Common Patterns

- Use Python type annotations compatible with Python 3.10, such as `list[str] | None`.
- Use module-level constants for fixed allowlists: `READ_COMMANDS`, `TRUSTED_COOKIE_DOMAINS`.
- Use `snake_case` for functions and variables; prefix internal helpers with `_`.
- Return integer CLI exit codes. Print user-facing errors to `sys.stderr`.
- Propagate the backend return code unchanged.
- Fail closed: reject unknown commands, malformed cookies, unsafe permissions, symlinks, and untrusted domains before execution.
- The backend runs in-process: `main()` validates first, applies `auth_token`/`ct0` to `os.environ` only after validation passes, then calls `xtractor_cli.backend.main()` (via its own `sys.argv` alignment) and returns its exit code. No subprocess, no shell strings.
- Keep credential values out of logs, errors, tests, documentation, and agent context.
- No async, dependency-injection framework, persistent state, cache, or argument parser exists. Add one only when a concrete requirement needs it.

## Important Files

- `install.sh`: one-command installer (venv, pip install of the git-pinned dependency, skill placement).
- `pyproject.toml`: package metadata, runtime dependency, wheel contents, and `xtractor` entry point.
- `xtractor_cli/backend.py`: project-owned launcher that resolves the live `UserTweets` queryId (24h disk cache at `~/.cache/xtractor/queryids.json`, overridable via `XTRACTOR_CACHE_DIR`; refreshes from the community twitter-openapi `placeholder.json`; falls back to a hardcoded constant on any network/cache failure) before delegating to the installed `twitter-cli` CLI.
- `xtractor_cli/cli.py`: command allowlist, cookie validation, optional proxy config resolution (`XTRACTOR_CONFIG`/`~/.config/xtractor/config.json`, overridable by `TWITTER_PROXY`), in-process backend delegation, and exit-code behavior.
- `tests/test_cli.py`: complete current behavioral test suite.
- `skill/SKILL.md`: supported reads, authentication workflow, and upstream failure policy.

## Runtime/Tooling Preferences

- Runtime: CPython `>=3.10`.
- Build backend: Hatchling.
- Package installation: `pip`; no lockfile or alternate package-manager configuration exists.
- Runtime dependency: `twitter-cli` pinned to `Blacksuite/twitter-cli@456c32512bd5129c5ea9bc8f3d8081b9cefc3bb4` for the authenticated ClientTransaction bootstrap (sends session cookies when fetching x.com). The project-owned `backend.py` override supplies the current live `UserTweets` queryId on top of this pin.
- Distribution and command name: `xtractor`; import package: `xtractor_cli`.
- Use `.venv/bin/python` and `.venv/bin/xtractor` for repository-local verification.
- No formatter, linter, type checker, or coverage tool is configured. Do not invent required commands for these tools.
- Treat `.env` and cookie exports as local credentials. Keep them owner-readable only with `chmod 600`.

## Testing & QA

Tests use stdlib `unittest` and `unittest.mock`; no pytest configuration exists. Add one focused test for each new observable contract or security boundary.

Follow current patterns in `tests/test_cli.py`:

- Use `tempfile.TemporaryDirectory()` for cookie files.
- Use fake credential values only.
- Patch `xtractor_cli.backend.main` to verify delegation without network access.

`build_zipapp.sh` builds the single-file `dist/xtractor.pyz` (zipapp bundling `xtractor_cli` plus all runtime dependencies; native extensions are extracted once to a hash-keyed cache dir under `~/.cache/xtractor/` at first run).

Before completion, run the unit suite and `compileall`. For CLI behavior changes, also run the actual `.venv/bin/xtractor` path. Current tests cover read-command forwarding, write rejection, cookie environment injection, unsafe permissions, symlink rejection, untrusted domains, missing backend, and missing commands. No coverage percentage is configured.
