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
    @patch("xtractor_cli.cli.subprocess.run")
    @patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", Path("/nonexistent/cookies.json"))
    def test_forwards_read_command_and_exit_code(self, run):
        run.return_value.returncode = 7

        self.assertEqual(main(["tweet", "123", "--json"]), 7)
        run.assert_called_once_with(
            [str(Path(sys.executable).with_name("python")), "-m", "xtractor_cli.backend",
             "tweet", "123", "--json"],
            check=False,
            env=None,
        )
    @patch("xtractor_cli.cli.subprocess.run")
    def test_loads_cookie_editor_json_into_child_env(self, run):
        run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "cookies.json"
            cookie_file.write_text(
                json.dumps(
                    [
                        {"name": "auth_token", "value": "fake-auth", "domain": ".x.com"},
                        {"name": "ct0", "value": "fake-ct0", "domain": ".x.com"},
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
                self.assertEqual(main(["status", "--yaml"]), 0)

        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["TWITTER_AUTH_TOKEN"], "fake-auth")
        self.assertEqual(child_env["TWITTER_CT0"], "fake-ct0")

    @patch("xtractor_cli.cli.subprocess.run")
    def test_rejects_cookie_file_accessible_by_group_or_others(self, run):
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

        run.assert_not_called()

    @unittest.skipIf(os.name == "nt", "symlink creation requires extra privileges")
    @patch("xtractor_cli.cli.subprocess.run")
    def test_rejects_cookie_file_symlink(self, run):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cookies.json"
            target.write_text("[]", encoding="utf-8")
            target.chmod(0o600)
            cookie_file = Path(directory) / "cookies-link.json"
            cookie_file.symlink_to(target)

            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(cookie_file)},
                clear=True,
            ):
                self.assertEqual(main(["status"]), 2)

        run.assert_not_called()
    @patch("xtractor_cli.cli.subprocess.run")
    def test_default_cookie_file_used_when_env_unset(self, run):
        run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "cookies.json"
            cookie_file.write_text(
                json.dumps(
                    [
                        {"name": "auth_token", "value": "fake-auth", "domain": ".x.com"},
                        {"name": "ct0", "value": "fake-ct0", "domain": ".x.com"},
                    ]
                ),
                encoding="utf-8",
            )
            cookie_file.chmod(0o600)

            with patch.dict(os.environ, {}, clear=True), patch(
                "xtractor_cli.cli.DEFAULT_COOKIE_FILE", cookie_file
            ):
                self.assertEqual(main(["status", "--yaml"]), 0)

        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["TWITTER_AUTH_TOKEN"], "fake-auth")
        self.assertEqual(child_env["TWITTER_CT0"], "fake-ct0")

    @patch("xtractor_cli.cli.subprocess.run")
    @patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", Path("/nonexistent/cookies.json"))
    def test_missing_default_cookie_file_keeps_browser_mode(self, run):
        run.return_value.returncode = 0
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(["status"]), 0)

        self.assertIsNone(run.call_args.kwargs["env"])

    @patch("xtractor_cli.cli.subprocess.run")
    def test_env_var_wins_over_default_cookie_file(self, run):
        run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as directory:
            default_cookie = Path(directory) / "cookies.json"
            default_cookie.write_text(
                json.dumps(
                    [
                        {"name": "auth_token", "value": "fake-auth", "domain": ".x.com"},
                        {"name": "ct0", "value": "fake-ct0", "domain": ".x.com"},
                    ]
                ),
                encoding="utf-8",
            )
            default_cookie.chmod(0o600)
            env_cookie = Path(directory) / "env-cookies.json"
            env_cookie.write_text(
                json.dumps(
                    [
                        {"name": "auth_token", "value": "env-auth", "domain": ".x.com"},
                        {"name": "ct0", "value": "env-ct0", "domain": ".x.com"},
                    ]
                ),
                encoding="utf-8",
            )
            env_cookie.chmod(0o600)

            with patch.dict(
                os.environ,
                {"XTRACTOR_COOKIE_FILE": str(env_cookie)},
                clear=True,
            ), patch("xtractor_cli.cli.DEFAULT_COOKIE_FILE", default_cookie):
                self.assertEqual(main(["status", "--yaml"]), 0)

        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["TWITTER_AUTH_TOKEN"], "env-auth")
        self.assertEqual(child_env["TWITTER_CT0"], "env-ct0")
    @patch("xtractor_cli.cli.subprocess.run")
    def test_rejects_cookie_names_from_untrusted_domains(self, run):
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

        run.assert_not_called()

    @patch("xtractor_cli.cli.subprocess.run")
    def test_rejects_write_command(self, run):
        self.assertEqual(main(["post", "nope"]), 2)
        run.assert_not_called()

    @patch("xtractor_cli.cli.subprocess.run", side_effect=FileNotFoundError)
    def test_reports_missing_backend(self, run):
        self.assertEqual(main(["status"]), 127)

    def test_requires_command(self):
        self.assertEqual(main([]), 2)


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

    @patch("xtractor_cli.cli.subprocess.run")
    def test_wrapper_launches_backend_bootstrap_module(self, run):
        run.return_value.returncode = 0

        # The wrapper must boot the project backend module (which applies
        # the live queryId overrides) rather than the upstream twitter CLI.
        self.assertEqual(main(["user-posts", "someone", "--max", "1"]), 0)
        cmd = run.call_args.args[0]
        self.assertIn("xtractor_cli.backend", " ".join(cmd[:4]))
        self.assertIn("user-posts", cmd)


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
