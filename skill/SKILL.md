---
name: xtractor
description: Use for read-only Twitter/X retrieval: tweets, replies, articles, search, timelines, bookmarks, lists, profiles, followers, and following.
---

# Xtractor

Run Twitter/X reads through `xtractor`. It forwards only read commands to `twitter-cli`.

## Authenticate

First run:

```bash
xtractor status --yaml
```

Local browser mode uses an existing X session from Arc, Chrome, Edge, Firefox, or Brave. Select browser/profile when needed:

```bash
TWITTER_BROWSER=chrome TWITTER_CHROME_PROFILE="Profile 2" xtractor status --yaml
```

For a remote machine, export `x.com` cookies as JSON with Cookie-Editor, transfer the file directly to that machine, then lock permissions before use:

```bash
chmod 600 ~/.config/xtractor/cookies.json
XTRACTOR_COOKIE_FILE=~/.config/xtractor/cookies.json xtractor status --yaml
```
If `~/.config/xtractor/cookies.json` exists, it is picked up automatically — no env var needed.

`xtractor` accepts a Cookie-Editor JSON array, checks file type/size/permissions and cookie domains, then exports only `auth_token` and `ct0` to the process environment. Keep cookie files outside repositories. Cookie values must stay outside agent context: never request them in chat or print, copy, commit, or return them.

## Proxy (optional)

Set once per machine in `~/.config/xtractor/config.json`:

```bash
mkdir -p ~/.config/xtractor
printf '{"proxy": "socks5h://user:pass@proxy-host:1080"}' > ~/.config/xtractor/config.json
chmod 600 ~/.config/xtractor/config.json
```

Allowed schemes: `http`, `https`, `socks4`, `socks5`, `socks5h` (`socks5h` preferred — DNS resolves at the proxy). `TWITTER_PROXY` env var overrides the config file; `XTRACTOR_CONFIG` points at a custom config location. Invalid config exits `2` with a specific error; unknown JSON keys are ignored.

When a proxy is set, x.com requests (API + `ClientTransaction` bootstrap) go through it. If a failure's upstream error mentions the proxy host, report it to the user — do not retry.

## Read

Prefer `--json` or `--yaml` for structured results.

```bash
xtractor tweet URL_OR_ID --json
xtractor article URL_OR_ID --json
xtractor search "QUERY" --max 20 --json
xtractor user USERNAME --json
xtractor user-posts USERNAME --max 20 --json
xtractor feed --max 20 --json
xtractor bookmarks --max 20 --json
xtractor list LIST_ID --json
xtractor followers USERNAME --max 50 --json
xtractor following USERNAME --max 50 --json
```

Follow returned cursors only when user requests more or all results. Stop and report rate limits; avoid aggressive retries.

## Failure policy

- Retry transient failure once.
- `401`/`403`: ask user to refresh browser login.
- `429`: stop; report rate limit.
- `404` or GraphQL/query mismatch: update the pinned dependency. `twitter-cli` is a git pin in `pyproject.toml`, not a globally installed tool. Bump the pinned commit, reinstall, then retry the read once:

```bash
.venv/bin/python -m pip install --force-reinstall .
```

Never install a global upstream `twitter-cli` (`uv tool upgrade` / `pipx upgrade`) over this project's backend: `xtractor_cli/backend.py` forces live GraphQL queryId overrides and cookie-bootstrap fixes on top of the pin, and an upgraded global install bypasses them.

Retry the original read once after reinstalling. Keep upstream errors visible; never replace failed reads with guessed or partial data.
