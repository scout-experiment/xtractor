<div align="center">

# xtractor

*A read-only Twitter/X CLI guardrail: it validates commands and cookie input, then delegates retrieval to a pinned [twitter-cli](https://github.com/public-clis/twitter-cli) backend.*

[Read-only guarantees](#read-only-guarantees) • [Quick start](#quick-start) • [Authentication](#authentication) • [Usage](#usage) • [Update policy](#update-policy)

</div>

## Read-only guarantees

`xtractor` never mutates your X account. Every invocation is checked against a command allowlist (`READ_COMMANDS` in `xtractor_cli/cli.py`) before anything runs:

- Commands outside the allowlist are rejected with exit code `2` — no subprocess is started.
- Missing backend executable exits `127`.
- The backend is launched with `subprocess.run()` on an argument list, never a shell string.

> [!IMPORTANT]
> Cookie values are credentials. They are never printed, logged, tested, committed, or returned; keep cookie files and `.env` outside repositories with `chmod 600`.

## Quick start

Install in one command (requires Python >= 3.10 and `git`; installs into a local `.venv` and copies the skill to `~/.agents/skills/xtractor/`):

```bash
git clone <repo-url> xtractor && cd xtractor
./install.sh
```

Verify with a first read:

```bash
.venv/bin/xtractor status --yaml
```

Alternative — manual setup:

```bash
python -m venv .venv
.venv/bin/python -m pip install --force-reinstall .
```

## Authentication

`xtractor` itself is unauthenticated; the pinned `twitter-cli` backend reads your X session.

**Browser-cookie mode (local machine):** the backend uses an existing X session from Arc, Chrome, Edge, Firefox, or Brave. Select a browser/profile with environment variables:

```bash
TWITTER_BROWSER=chrome TWITTER_CHROME_PROFILE="Profile 2" xtractor status --yaml
```

**Cookie file mode (remote machines):** export `x.com` cookies as JSON with Cookie-Editor, transfer the file directly to the machine, then lock permissions:

```bash
chmod 600 ~/.config/xtractor/cookies.json
XTRACTOR_COOKIE_FILE=~/.config/xtractor/cookies.json xtractor status --yaml
```

Before any cookie reaches the backend, `xtractor_cli/cli.py` validates the file: it must be a regular file (symlinks rejected), owner-readable (`chmod 600`), at most 1 MiB, valid UTF-8 JSON as a Cookie-Editor array, and every cookie domain must be `x.com`, `twitter.com`, or a subdomain. Only `auth_token` and `ct0` are extracted and passed to the child-process environment; nothing else from the file is forwarded.

## Usage

Prefer `--json` or `--yaml` for structured results. Supported read commands:

| Command | Example |
| --- | --- |
| `status` | `xtractor status --yaml` |
| `whoami` | `xtractor whoami --json` |
| `tweet` | `xtractor tweet URL_OR_ID --json` |
| `article` | `xtractor article URL_OR_ID --json` |
| `search` | `xtractor search "QUERY" --max 20 --json` |
| `user` | `xtractor user USERNAME --json` |
| `user-posts` | `xtractor user-posts USERNAME --max 20 --json` |
| `feed` | `xtractor feed --max 20 --json` |
| `bookmarks` | `xtractor bookmarks --max 20 --json` |
| `list` | `xtractor list LIST_ID --json` |
| `followers` | `xtractor followers USERNAME --max 50 --json` |
| `following` | `xtractor following USERNAME --max 50 --json` |
| `show` | resolves a cached result index to a tweet |

Follow returned cursors only when you need more results. On `401`/`403`, refresh your browser login; on `429`, stop and wait out the rate limit — avoid aggressive retries.

## Query ID refresh

X rotates its GraphQL `queryId`s over time. The pinned `twitter-cli` dependency hardcodes a fallback `UserTweets` ID that has gone stale, and X now answers that stale ID with HTTP 200 and an unrelated timeline — so upstream's error-based refresh path never triggers. `xtractor_cli/backend.py` therefore forces the queryId currently served by live x.com bundles and re-asserts it on every backend invocation, while keeping the pinned fork's authenticated `ClientTransaction` bootstrap intact. Other operations still resolve through the fork's own sources: a community-maintained `placeholder.json` and a scan of x.com's JavaScript bundles.

## Update policy

`twitter-cli` is a git pin in `pyproject.toml`, not a globally installed tool. On `404` or GraphQL/query mismatches, bump the pinned commit and reinstall from this repository:

```bash
.venv/bin/python -m pip install --force-reinstall .
```

Never install a global upstream `twitter-cli` (`uv tool upgrade` / `pipx upgrade`) over this project's backend: `xtractor_cli/backend.py` applies queryId overrides and cookie-bootstrap fixes on top of the pin, and a globally upgraded install bypasses them.

## Development

Run tests and syntax checks with the repository-local interpreter:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q xtractor_cli tests
```

The suite uses stdlib `unittest` and mocks `subprocess.run`, so no network access is needed; it covers read-command forwarding, write rejection, cookie validation (permissions, symlinks, untrusted domains), missing backend, and missing commands. The console script runs code from the installed wheel — reinstall after changing `xtractor_cli/` before CLI smoke tests. Build distributions with `python -m build` (Hatchling) if the `build` package is installed.
