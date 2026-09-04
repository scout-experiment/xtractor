import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch

from twitter_cli.graphql import FALLBACK_QUERY_IDS

from xtractor_cli.cli import main


class MainTests(unittest.TestCase):
    """Wrapper delegates to the project backend in-process (zipapp-safe)."""

    def _cookie_file(self, directory: str, name: str = "cookies.json", **values: str) -> Path:
        cookie_file = Path(directory) / name
        defaults = {
            "auth_token": "fake-auth",
            "ct0": "fake-ct0",
        }
        defaults.update(values)
        cookie_file.write_text(
            json.dumps(
                [
                    {"name": name_, "value": value, "domain": ".x.com"}
                    for name_, value in defaults.items()
                ]
            ),
            encoding="utf-8",
        )
        cookie_file.chmod(0o600)
        return cookie_file

    def _backend_main_recorder(self, return_value: int = 0):
        mock = patch(
            "xtractor_cli.backend.main",
            side_effect=lambda: (self.recorded_env.update(os.environ), return_value)[1],
        )
        return mock

    def setUp(self) -> None:
        self.recorded_env: dict[str, str] = {}

    @patch("xtractor_cli.backend.main", return_value=7)
    @patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", Path("/nonexistent/cookies.json"))
    def test_forwards_read_command_via_sys_argv(self, backend_main):
        self.assertEqual(main(["tweet", "123", "--json"]), 7)
        backend_main.assert_called_once_with()

    def test_rejects_non_read_command_before_backend(self):
        with patch("xtractor_cli.backend.main") as backend_main:
            self.assertEqual(main(["post", "nope"]), 2)
        backend_main.assert_not_called()

    def test_loads_cookie_editor_json_into_environ(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = self._cookie_file(directory)
            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(cookie_file)},
                clear=True,
            ), self._backend_main_recorder():
                self.assertEqual(main(["status", "--yaml"]), 0)

        self.assertEqual(self.recorded_env.get("TWITTER_AUTH_TOKEN"), "fake-auth")
        self.assertEqual(self.recorded_env.get("TWITTER_CT0"), "fake-ct0")

    @patch("xtractor_cli.backend.main")
    def test_rejects_cookie_file_accessible_by_group_or_others(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "cookies.json"
            cookie_file.write_text("[]", encoding="utf-8")
            cookie_file.chmod(0o644)

            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(cookie_file)},
                clear=True,
            ):
                self.assertEqual(main(["status"]), 2)

        backend_main.assert_not_called()

    @unittest.skipIf(os.name == "nt", "symlink creation requires extra privileges")
    @patch("xtractor_cli.backend.main")
    def test_rejects_cookie_file_symlink(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cookies.json"
            target.write_text("[]", encoding="utf-8")
            target.chmod(0o600)
            cookie_file = Path(directory) / "cookies-link.json"
            cookie_file.symlink_to(target)

    def test_default_cookie_file_used_when_env_unset(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = self._cookie_file(directory)

            with patch.dict(os.environ, {}, clear=True), patch(
                "xtractor_cli.cli.DEFAULT_COOKIE_FILE", cookie_file
            ), self._backend_main_recorder():
                self.assertEqual(main(["status", "--yaml"]), 0)

        self.assertEqual(self.recorded_env.get("TWITTER_AUTH_TOKEN"), "fake-auth")
        self.assertEqual(self.recorded_env.get("TWITTER_CT0"), "fake-ct0")

    @patch("xtractor_cli.backend.main", return_value=0)
    @patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", Path("/nonexistent/cookies.json"))
    def test_missing_default_cookie_file_keeps_browser_mode(self, backend_main):
        snapshot = dict(os.environ)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(["status"]), 0)

        self.assertEqual(os.environ, snapshot)

    def test_env_var_wins_over_default_cookie_file(self):
        with tempfile.TemporaryDirectory() as directory:
            default_cookie = self._cookie_file(directory)
            env_cookie = self._cookie_file(
                directory, name="env-cookies.json",
                auth_token="env-auth", ct0="env-ct0",
            )

            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(env_cookie)},
                clear=True,
            ), patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", default_cookie), \
            self._backend_main_recorder():
                self.assertEqual(main(["status", "--yaml"]), 0)

        self.assertEqual(self.recorded_env.get("TWITTER_AUTH_TOKEN"), "env-auth")
        self.assertEqual(self.recorded_env.get("TWITTER_CT0"), "env-ct0")

    @patch("xtractor_cli.backend.main")
    def test_rejects_cookie_names_from_untrusted_domains(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "cookies.json"
            cookie_file.write_text(
                json.dumps(
                    [
                        {"name": "auth_token", "value": "fake-auth", "domain": "evil.example"},
                        {"name": "ct0", "value": "fake-ct0", "domain": "evil.example"},
                    ]
                ),
                encoding="utf-8",
            )
            cookie_file.chmod(0o600)

            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(cookie_file)},
                clear=True,
            ):
                self.assertEqual(main(["status"]), 2)

        backend_main.assert_not_called()

    def test_requires_command(self):
        with patch("xtractor_cli.backend.main") as backend_main:
            self.assertEqual(main([]), 2)
        backend_main.assert_not_called()

    @patch("xtractor_cli.backend.main", side_effect=ImportError("twitter_cli missing"))
    def test_reports_missing_backend(self, backend_main):
        self.assertEqual(main(["status"]), 127)

    @patch("xtractor_cli.backend.main", return_value=0)
    def test_does_not_mutate_environ_before_validation(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "cookies.json"
            cookie_file.write_text("[]", encoding="utf-8")
            cookie_file.chmod(0o644)
            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(cookie_file)},
                clear=True,
            ):
                self.assertEqual(main(["status"]), 2)
        self.assertNotIn("TWITTER_AUTH_TOKEN", os.environ)

    def test_argv_argument_alignment(self):
        """Explicit argv lands in sys.argv for the backend's click parser."""
        seen: dict[str, object] = {}

        def fake_backend_main() -> int:
            seen["argv"] = list(sys.argv)
            return 3

        with patch("xtractor_cli.backend.main", side_effect=fake_backend_main), patch(
            "xtractor_cli.cli.DEFAULT_COOKIE_FILE", Path("/nonexistent/cookies.json")
        ):
            self.assertEqual(main(["user", "someone", "--json"]), 3)



class ProxyConfigTests(unittest.TestCase):
    """Proxy resolution: TWITTER_PROXY env > config file proxy key > unset."""

    def _config_file(self, directory: str, payload: dict[str, object], name: str = "config.json") -> Path:
        config_file = Path(directory) / name
        config_file.write_text(json.dumps(payload), encoding="utf-8")
        config_file.chmod(0o600)
        return config_file

    def _backend_main_recorder(self, return_value: int = 0):
        return patch(
            "xtractor_cli.backend.main",
            side_effect=lambda: (self.recorded_env.update(os.environ), return_value)[1],
        )

    def setUp(self) -> None:
        self.recorded_env: dict[str, str] = {}

    @patch("xtractor_cli.backend.main")
    def test_config_proxy_used_when_env_unset(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            config_file = self._config_file(directory, {"proxy": "socks5h://proxy.example:1080"})
            with patch.dict(os.environ, {"XTRACTOR_CONFIG": str(config_file)}, clear=True), \
            self._backend_main_recorder():
                self.assertEqual(main(["status"]), 0)

        self.assertEqual(self.recorded_env.get("TWITTER_PROXY"), "socks5h://proxy.example:1080")

    @patch("xtractor_cli.cli.DEFAULT_CONFIG_FILE", Path("/nonexistent/config.json"))
    def test_env_proxy_wins_over_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_file = self._config_file(directory, {"proxy": "socks5h://config.example:1080"})
            with patch.dict(
                os.environ,
                {"XTRACTOR_CONFIG": str(config_file), "TWITTER_PROXY": "socks5h://env.example:1080"},
                clear=True,
            ), self._backend_main_recorder():
                self.assertEqual(main(["status"]), 0)

        self.assertEqual(self.recorded_env.get("TWITTER_PROXY"), "socks5h://env.example:1080")

    @patch("xtractor_cli.backend.main", return_value=0)
    def test_missing_config_file_leaves_proxy_unset(self, backend_main):
        snapshot = dict(os.environ)
        with patch.dict(os.environ, {"XTRACTOR_CONFIG": "/nonexistent/config.json"}, clear=True):
            self.assertEqual(main(["status"]), 0)

        self.assertEqual(os.environ, snapshot)
        self.assertNotIn("TWITTER_PROXY", os.environ)

    @patch("xtractor_cli.backend.main")
    def test_rejects_invalid_proxy_scheme(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            config_file = self._config_file(directory, {"proxy": "ftp://x"})
            with patch.dict(os.environ, {"XTRACTOR_CONFIG": str(config_file)}, clear=True), \
            patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(main(["status"]), 2)

        backend_main.assert_not_called()
        self.assertIn("xtractor: config file:", stderr.getvalue())

    @unittest.skipIf(os.name == "nt", "symlink creation requires extra privileges")
    @patch("xtractor_cli.backend.main")
    def test_rejects_config_file_symlink(self, backend_main):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config.json"
            target.write_text(json.dumps({"proxy": "socks5h://proxy.example:1080"}), encoding="utf-8")
            target.chmod(0o600)
            config_file = Path(directory) / "config-link.json"
            config_file.symlink_to(target)

            with patch.dict(os.environ, {"XTRACTOR_CONFIG": str(config_file)}, clear=True):
                self.assertEqual(main(["status"]), 2)

        backend_main.assert_not_called()

    def test_extra_keys_ignored_and_proxy_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            config_file = self._config_file(
                directory, {"proxy": "socks5h://proxy.example:1080", "future_key": 1}
            )
            with patch.dict(os.environ, {"XTRACTOR_CONFIG": str(config_file)}, clear=True), \
            self._backend_main_recorder():
                self.assertEqual(main(["status"]), 0)

        self.assertEqual(self.recorded_env.get("TWITTER_PROXY"), "socks5h://proxy.example:1080")


class BackendRegressionTests(unittest.TestCase):
    def test_backend_resolves_live_usertweets_query_id(self):
        import importlib

        import twitter_cli.graphql as graphql

        stale = "36rb3Xj3iJ64Q-9wKDjCcQ"  # poisoned ID, no longer usable
        live = "SXVCYB8XHSS25nzIljNtZA"  # served by live x.com bundles

        with tempfile.TemporaryDirectory() as directory, patch(
            "xtractor_cli.backend.urllib.request.urlopen",
            side_effect=OSError("no network in tests"),
        ):
            # Simulate the dependency's poisoned state before the override runs.
            graphql.FALLBACK_QUERY_IDS["UserTweets"] = stale
            graphql._cached_query_ids.pop("UserTweets", None)
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                importlib.reload(importlib.import_module("xtractor_cli.backend"))

            # The override must win over whatever fallback the dependency ships.
            self.assertEqual(
                graphql.FALLBACK_QUERY_IDS["UserTweets"],
                live,
            )
            self.assertEqual(
                graphql._resolve_query_id("UserTweets", prefer_fallback=True),
                live,
            )

    @patch("xtractor_cli.backend.main", return_value=0)
    @patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", Path("/nonexistent/cookies.json"))
    def test_wrapper_calls_backend_bootstrap_in_process(self, backend_main):
        # The wrapper must call the project backend module (which applies
        # the live queryId overrides) rather than the upstream twitter CLI,
        # in-process so a zipapp works without a sibling interpreter.
        self.assertEqual(main(["user-posts", "someone", "--max", "1"]), 0)
        backend_main.assert_called_once_with()

        import xtractor_cli.backend  # noqa: F401  (bootstrap ran on import)
        self.assertIn(
            "SXVCYB8XHSS25nzIljNtZA",
            __import__("twitter_cli.graphql", fromlist=["x"]).FALLBACK_QUERY_IDS["UserTweets"],
        )


class QueryIdCacheTests(unittest.TestCase):
    """queryId cache precedence: fresh cache > network > hardcoded constant."""

    LIVE_ID = "SXVCYB8XHSS25nzIljNtZA"

    def _write_cache(self, directory: str, payload: str) -> None:
        cache = Path(directory) / "queryids.json"
        cache.write_text(payload, encoding="utf-8")
        cache.chmod(0o600)

    def _reload_backend(self):
        import importlib

        import xtractor_cli.backend as backend

        return importlib.reload(backend)

    def test_fresh_cache_wins_without_network(self):
        import time as time_module

        with tempfile.TemporaryDirectory() as directory:
            fetched_at = time_module.time()
            self._write_cache(
                directory,
                json.dumps(
                    {
                        "fetched_at": fetched_at,
                        "query_ids": {"UserTweets": "cachedQID1234567890"},
                    }
                ),
            )
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                with patch(
                    "xtractor_cli.backend.urllib.request.urlopen"
                ) as urlopen:
                    backend = self._reload_backend()
                    urlopen.assert_not_called()
                    self.assertEqual(
                        backend.resolve_query_id_overrides(),
                        {"UserTweets": "cachedQID1234567890"},
                    )

    def test_stale_cache_falls_back_to_hardcoded_constant(self):
        import time as time_module

        with tempfile.TemporaryDirectory() as directory:
            fetched_at = time_module.time() - 25 * 60 * 60
            self._write_cache(
                directory,
                json.dumps(
                    {
                        "fetched_at": fetched_at,
                        "query_ids": {"UserTweets": "cachedQID1234567890"},
                    }
                ),
            )
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                with patch(
                    "xtractor_cli.backend.urllib.request.urlopen",
                    side_effect=OSError("no network in tests"),
                ):
                    backend = self._reload_backend()
                    self.assertEqual(
                        backend.resolve_query_id_overrides(),
                        {"UserTweets": self.LIVE_ID},
                    )

    def test_corrupt_cache_falls_back_to_hardcoded_constant(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_cache(directory, "{not json")
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                with patch(
                    "xtractor_cli.backend.urllib.request.urlopen",
                    side_effect=OSError("no network in tests"),
                ):
                    backend = self._reload_backend()
                    self.assertEqual(
                        backend.resolve_query_id_overrides(),
                        {"UserTweets": self.LIVE_ID},
                    )

    def test_missing_cache_and_network_failure_falls_back_on_import(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                with patch(
                    "xtractor_cli.backend.urllib.request.urlopen",
                    side_effect=OSError("no network in tests"),
                ):
                    backend = self._reload_backend()
                    self.assertEqual(
                        backend.resolve_query_id_overrides(),
                        {"UserTweets": self.LIVE_ID},
                    )

    def test_cache_symlink_is_ignored(self):
        import time as time_module

        if os.name == "nt":
            self.skipTest("symlink creation requires extra privileges")
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as other:
            target = Path(other) / "queryids.json"
            target.write_text(
                json.dumps(
                    {
                        "fetched_at": time_module.time(),
                        "query_ids": {"UserTweets": "cachedQID1234567890"},
                    }
                ),
                encoding="utf-8",
            )
            link = Path(directory) / "queryids.json"
            link.symlink_to(target)
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                with patch(
                    "xtractor_cli.backend.urllib.request.urlopen",
                    side_effect=OSError("no network in tests"),
                ):
                    backend = self._reload_backend()
                    self.assertEqual(
                        backend.resolve_query_id_overrides(),
                        {"UserTweets": self.LIVE_ID},
                    )

    def test_successful_fetch_writes_cache_with_restrictive_perms(self):
        import time as time_module

        payload = json.dumps(
            {"UserTweets": {"queryId": "fetchedQID123456789"}, "other": {"queryId": "x"}}
        ).encode("utf-8")
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = payload
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XTRACTOR_CACHE_DIR": directory}):
                with patch(
                    "xtractor_cli.backend.urllib.request.urlopen",
                    return_value=response,
                ):
                    backend = self._reload_backend()
                    self.assertEqual(
                        backend.resolve_query_id_overrides()["UserTweets"],
                        "fetchedQID123456789",
                    )
            cache = Path(directory) / "queryids.json"
            self.assertTrue(cache.is_file())
            stored = json.loads(cache.read_text(encoding="utf-8"))
            self.assertLess(time_module.time() - stored["fetched_at"], 60)
            self.assertEqual(stored["query_ids"]["UserTweets"], "fetchedQID123456789")
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
