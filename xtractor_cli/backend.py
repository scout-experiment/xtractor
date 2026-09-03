"""Project-owned launcher for the twitter-cli backend.

X rotates GraphQL queryIds. The pinned twitter-cli dependency hardcodes a
fallback UserTweets queryId that has gone stale; X now answers that ID with
HTTP 200 and an unrelated timeline, so upstream's error-based refresh path
never triggers. Before handing control to the upstream CLI (which keeps the
authenticated ClientTransaction bootstrap intact), we resolve the current
UserTweets queryId and force it over the dependency's stale fallbacks.

Resolution order: fresh disk cache (24h TTL) > live fetch from the
community twitter-openapi placeholder.json > LIVE_QUERY_ID_OVERRIDES
hardcoded constant > the dependency's stale IDs. Network failures never
crash startup; every failure path degrades to the hardcoded constant.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request
from pathlib import Path

import twitter_cli.graphql as _graphql

LIVE_QUERY_ID_OVERRIDES = {
    "UserTweets": "SXVCYB8XHSS25nzIljNtZA",
}

QUERY_IDS_URL = (
    "https://raw.githubusercontent.com/fa0311/"
    "twitter-openapi/refs/heads/main/src/config/placeholder.json"
)
CACHE_TTL_SECONDS = 24 * 60 * 60
FETCH_TIMEOUT_SECONDS = 5


def _cache_dir() -> Path:
    return Path(os.environ.get("XTRACTOR_CACHE_DIR", Path.home() / ".cache" / "xtractor"))


def _load_cached_query_ids(now: float) -> dict[str, str] | None:
    """Return cached queryIds if fresh and well-formed, else None.

    Fail closed: symlinks, unreadable, stale, or corrupt files are ignored.
    """
    cache_file = _cache_dir() / "queryids.json"
    try:
        if cache_file.is_symlink() or not cache_file.is_file():
            return None
        stat = cache_file.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            return None
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        fetched_at = payload["fetched_at"]
        query_ids = payload["query_ids"]
        if not isinstance(fetched_at, (int, float)) or now - fetched_at > CACHE_TTL_SECONDS:
            return None
        if not isinstance(query_ids, dict):
            return None
        clean = {
            name: qid
            for name, qid in query_ids.items()
            if isinstance(name, str) and isinstance(qid, str) and qid
        }
        if "UserTweets" not in clean:
            return None
        return clean
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _fetch_query_ids() -> dict[str, str] | None:
    """Fetch operation queryIds from twitter-openapi; None on any failure."""
    try:
        with urllib.request.urlopen(QUERY_IDS_URL, timeout=FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        query_ids = {
            name: operation["queryId"]
            for name, operation in payload.items()
            if isinstance(operation, dict)
            and isinstance(operation.get("queryId"), str)
            and operation["queryId"]
        }
        return query_ids or None
    except Exception:
        return None


def _store_query_ids(query_ids: dict[str, str]) -> None:
    """Best-effort cache write with restrictive permissions (0600)."""
    try:
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        descriptor, tmp_path = tempfile.mkstemp(dir=cache_dir, prefix=".queryids-")
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"fetched_at": time.time(), "query_ids": query_ids}, handle)
            os.replace(tmp_path, cache_dir / "queryids.json")
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError:
        pass


def resolve_query_id_overrides() -> dict[str, str]:
    """Resolve current queryIds: cache > network > hardcoded constant."""
    cached = _load_cached_query_ids(time.time())
    if cached is not None:
        return cached
    fetched = _fetch_query_ids()
    if fetched is not None and "UserTweets" in fetched:
        _store_query_ids(fetched)
        return fetched
    return dict(LIVE_QUERY_ID_OVERRIDES)


def apply_query_id_overrides() -> None:
    """Force resolved live queryIds over the dependency's stale fallbacks."""
    overrides = resolve_query_id_overrides()
    _graphql.FALLBACK_QUERY_IDS.update(overrides)
    for name in overrides:
        _graphql._cached_query_ids.pop(name, None)


apply_query_id_overrides()


def main() -> int:
    from twitter_cli.cli import cli

    return cli()


if __name__ == "__main__":
    raise SystemExit(main())

