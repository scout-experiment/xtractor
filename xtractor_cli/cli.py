import json
import os
import stat
import subprocess
import sys
from pathlib import Path

READ_COMMANDS = frozenset(
    {
        "article",
        "bookmarks",
        "feed",
        "followers",
        "following",
        "list",
        "search",
        "show",
        "status",
        "tweet",
        "user",
        "user-posts",
        "whoami",
    }
)
TRUSTED_COOKIE_DOMAINS = {"x.com", "twitter.com"}
DEFAULT_COOKIE_FILE = Path.home() / ".config" / "xtractor" / "cookies.json"


class CookieFileError(ValueError):
    pass


def _trusted_cookie_domain(domain: object) -> bool:
    value = str(domain).lstrip(".").lower()
    return any(value == trusted or value.endswith(f".{trusted}") for trusted in TRUSTED_COOKIE_DOMAINS)


def _cookie_env(path: Path) -> dict[str, str]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
            raise CookieFileError("cookie file must be a regular file, not a symlink")
        descriptor = os.open(path, flags)
    except CookieFileError:
        raise
    except OSError as exc:
        raise CookieFileError(f"cannot read cookie file: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise CookieFileError("cookie file must be a regular file, not a symlink")
        if os.name != "nt" and info.st_mode & 0o077:
            raise CookieFileError("cookie file permissions must be 0600")
        raw = os.read(descriptor, 1024 * 1024 + 1)
    finally:
        os.close(descriptor)
    if len(raw) > 1024 * 1024:
        raise CookieFileError("cookie file exceeds 1 MiB")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CookieFileError("cookie file must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, list):
        raise CookieFileError("cookie file must be a Cookie-Editor JSON array")

    cookies: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict) or not _trusted_cookie_domain(item.get("domain", "")):
            continue
        name = item.get("name")
        value = item.get("value")
        if name in {"auth_token", "ct0"} and isinstance(value, str) and value:
            cookies[name] = value
    if set(cookies) != {"auth_token", "ct0"}:
        raise CookieFileError("cookie file lacks x.com auth_token or ct0")
    return {
        "TWITTER_AUTH_TOKEN": cookies["auth_token"],
        "TWITTER_CT0": cookies["ct0"],
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in READ_COMMANDS:
        command = args[0] if args else "<missing>"
        print(f"xtractor: read-only command required; rejected: {command}", file=sys.stderr)
        return 2

    child_env = None
    cookie_file = os.environ.get("XTRACTOR_COOKIE_FILE") or (
        DEFAULT_COOKIE_FILE if DEFAULT_COOKIE_FILE.is_file() else None
    )
    if cookie_file:
        try:
            child_env = os.environ.copy()
            child_env.update(_cookie_env(Path(cookie_file).expanduser()))
        except CookieFileError as exc:
            print(f"xtractor: {exc}", file=sys.stderr)
            return 2

    try:
        backend = Path(sys.executable).with_name("python")
        cmd = [str(backend), "-m", "xtractor_cli.backend", *args]
        return subprocess.run(cmd, check=False, env=child_env).returncode
    except FileNotFoundError:
        print("xtractor: twitter-cli is not installed", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
