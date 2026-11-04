from __future__ import annotations

import json
import os
import io
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from douda.cli import (
    DEFAULT_LEADERBOARD_URL,
    LEADERBOARD_LIMIT,
    _QUIT_QUOTES,
    _leaderboard_url,
    _load_saved_player_name,
    _print_leaderboard,
    _print_quit_quote,
    _save_player_name,
    main,
)
from douda.leaderboard import LeaderboardCache
from douda.terminal import reset, visible_width


class LeaderboardUrlTests(unittest.TestCase):
    def test_saved_name_is_reused_on_next_launch_for_global_rank_lookup(self) -> None:
        reset()
        self.addCleanup(reset)
        with tempfile.TemporaryDirectory() as config_home, patch.dict(
            os.environ, {"APPDATA": config_home}
        ):
            _save_player_name("Nayla")
            with patch("douda.cli.sys.argv", ["douda"]), patch(
                "douda.cli.LeaderboardCache"
            ) as cache_class, patch(
                "douda.cli.play", return_value=(0, False)
            ) as play, patch("douda.cli._print_quit_quote"):
                cache_class.return_value.snapshot.return_value = ([], None)
                main()
            self.assertEqual(_load_saved_player_name(), "Nayla")

        self.assertEqual(cache_class.call_args.args[1], "Nayla")
        self.assertEqual(play.call_args.args[0], "Nayla")

    def test_game_asks_for_name_only_after_a_loss_and_reuses_it_on_replay(self) -> None:
        reset()
        self.addCleanup(reset)
        with tempfile.TemporaryDirectory() as config_home, patch.dict(
            os.environ, {"APPDATA": config_home}
        ), patch("douda.cli.sys.argv", ["douda"]), patch(
            "douda.cli.LeaderboardCache"
        ) as cache_class, patch(
            "douda.cli.play", side_effect=[(10, True), (0, False)]
        ) as play, patch(
            "douda.cli.submit_score", return_value={"id": 12}
        ) as submit, patch(
            "douda.cli.wait_for_replay", return_value=True
        ), patch("douda.cli._print_quit_quote"), patch(
            "builtins.input", return_value="Ada"
        ) as prompt:
            cache_class.return_value.snapshot.return_value = ([], None)
            main()
            self.assertEqual(_load_saved_player_name(), "Ada")

        prompt.assert_called_once()
        submit.assert_called_once_with(
            "https://douda-cli.onrender.com", "Ada", 10
        )
        self.assertEqual(
            [call.args[0] for call in play.call_args_list], ["Player", "Ada"]
        )
        cache_class.return_value.set_player_name.assert_called_once_with("Ada")
        cache_class.return_value.focus_score.assert_called_once_with(12)

    def test_leaderboard_does_not_assume_a_player_name(self) -> None:
        reset()
        self.addCleanup(reset)
        with tempfile.TemporaryDirectory() as config_home, patch.dict(
            os.environ, {"APPDATA": config_home}
        ), patch("douda.cli.sys.argv", ["douda", "leaderboard"]), patch(
            "douda.cli._print_leaderboard", return_value=0
        ) as print_board:
            with self.assertRaises(SystemExit) as exit_error:
                main()

        self.assertEqual(exit_error.exception.code, 0)
        self.assertIsNone(print_board.call_args.args[3])

    def test_quit_prints_a_random_motivational_quote(self) -> None:
        output = io.StringIO()
        with patch("douda.cli.random.choice", return_value=_QUIT_QUOTES[0]), patch(
            "douda.cli.sys.stdout", output
        ):
            _print_quit_quote()

        self.assertEqual(output.getvalue(), f"✨ {_QUIT_QUOTES[0]} ✨\n")

    def test_quit_quote_sparkles_with_colors_on_tty(self) -> None:
        output = io.StringIO()
        output.isatty = lambda: True  # type: ignore[method-assign]
        with patch("douda.cli.random.choice", return_value=_QUIT_QUOTES[0]), patch(
            "douda.cli.sys.stdout", output
        ):
            _print_quit_quote()

        self.assertIn("\033[1;33m✨\033[0m", output.getvalue())
        self.assertIn(f"\033[1;35m{_QUIT_QUOTES[0]}\033[0m", output.getvalue())

    def test_quit_quote_respects_no_color(self) -> None:
        output = io.StringIO()
        output.isatty = lambda: True  # type: ignore[method-assign]
        with patch.dict(os.environ, {"NO_COLOR": ""}), patch(
            "douda.cli.random.choice", return_value=_QUIT_QUOTES[0]
        ), patch("douda.cli.sys.stdout", output):
            _print_quit_quote()

        self.assertNotIn("\033[", output.getvalue())

    def test_defaults_to_shared_leaderboard(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_leaderboard_url(), DEFAULT_LEADERBOARD_URL)

    def test_leaderboard_command_uses_saved_player_name(self) -> None:
        reset()
        self.addCleanup(reset)
        with tempfile.TemporaryDirectory() as config_home, patch.dict(
            os.environ, {"APPDATA": config_home}
        ):
            _save_player_name("Nayla")
            with patch("douda.cli.sys.argv", ["douda", "leaderboard"]), patch(
                "douda.cli._print_leaderboard", return_value=0
            ) as print_board:
                with self.assertRaises(SystemExit):
                    main()

        self.assertEqual(print_board.call_args.args[3], "Nayla")

    def test_environment_variable_overrides_default(self) -> None:
        with patch.dict(
            os.environ,
            {"DOUDA_LEADERBOARD_URL": "https://scores.example.com/"},
            clear=True,
        ):
            self.assertEqual(_leaderboard_url(), "https://scores.example.com")

    def test_leaderboard_prints_top_scores_and_personal_rank(self) -> None:
        result = {
            "total": 20,
            "scores": [
                {"rank": 1, "name": "Ada", "score": 90},
                {"rank": 2, "name": "Lin", "score": 80},
                {"rank": 3, "name": "Sam", "score": 70},
                {"rank": 4, "name": "Jo", "score": 60},
                {"rank": 5, "name": "Kim", "score": 50},
                {"rank": 6, "name": "Lee", "score": 40},
                {"rank": 7, "name": "Max", "score": 30},
            ],
            "player": {"rank": 17, "score": 20},
        }
        output = io.StringIO()

        with patch("douda.cli.get_scores", return_value=result) as get_scores, patch(
            "douda.cli.sys.stdout", output
        ):
            status = _print_leaderboard(
                "https://example.com", LEADERBOARD_LIMIT, 0, "Ada"
            )

        rendered = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("GLOBAL TOP 5", rendered)
        self.assertIn("1. Ada", rendered)
        self.assertIn("2. Lin", rendered)
        self.assertIn("3. Sam", rendered)
        self.assertIn("4. Jo", rendered)
        self.assertIn("5. Kim", rendered)
        self.assertNotIn("6. Lee", rendered)
        self.assertIn("17. Ada", rendered)
        get_scores.assert_called_once_with(
            "https://example.com", LEADERBOARD_LIMIT, 0, "Ada"
        )
        self.assertEqual(
            rendered.count("|                  .                   |"), 3
        )
        self.assertEqual(
            {visible_width(line) for line in rendered.splitlines()},
            {40},
        )

    def test_leaderboard_plain_mode_has_no_ansi_and_aligns(self) -> None:
        result = {
            "total": 20,
            "scores": [
                {"rank": 1, "name": "Ada", "score": 90},
                {"rank": 2, "name": "Lin", "score": 80},
                {"rank": 3, "name": "Sam", "score": 70},
                {"rank": 4, "name": "Jo", "score": 60},
                {"rank": 5, "name": "Kim", "score": 50},
                {"rank": 6, "name": "Lee", "score": 40},
                {"rank": 7, "name": "Max", "score": 30},
            ],
            "player": {"rank": 17, "name": "Naila", "score": 30},
        }
        output = io.StringIO()
        output.isatty = lambda: True  # type: ignore[method-assign]

        reset()
        from douda import terminal

        terminal.configure(force_plain=True)
        try:
            with patch("douda.cli.get_scores", return_value=result), patch(
                "douda.cli.sys.stdout", output
            ):
                _print_leaderboard(
                    "https://example.com", LEADERBOARD_LIMIT, 0, "Naila"
                )
        finally:
            reset()

        rendered = output.getvalue()
        self.assertNotIn("\033[", rendered)
        self.assertIn("17. Naila", rendered)
        self.assertEqual(
            rendered.count("|                  .                   |"), 3
        )
        self.assertEqual(
            {visible_width(line) for line in rendered.splitlines()},
            {40},
        )


class LeaderboardCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_path = Path(self.temp_dir.name) / "leaderboard-cache.json"

    def test_refresh_reloads_the_latest_scores(self) -> None:
        first = {
            "scores": [{"rank": 1, "name": "Ada", "score": 10}],
            "player": {"rank": 1, "name": "Ada", "score": 10},
        }
        second = {
            "scores": [{"rank": 1, "name": "Bob", "score": 20}],
            "player": {"rank": 1, "name": "Bob", "score": 20},
        }
        with patch("douda.leaderboard.get_scores", side_effect=[first, second]):
            cache = LeaderboardCache(
                "https://example.com", "Ada", cache_path=self.cache_path
            )
            cache.refresh(block=True)
            self.assertEqual(cache.snapshot()[0][0]["name"], "Ada")
            self.assertFalse(cache.is_loading())
            cache.refresh(block=True)
            self.assertEqual(cache.snapshot()[0][0]["name"], "Bob")
            self.assertFalse(cache.is_loading())

    def test_refresh_does_not_block_gameplay(self) -> None:
        release = threading.Event()

        def slow_scores(*args: object, **kwargs: object) -> dict[str, object]:
            release.wait(2)
            return {"scores": [], "player": None}

        with patch("douda.leaderboard.get_scores", side_effect=slow_scores):
            cache = LeaderboardCache(
                "https://example.com", "Ada", cache_path=self.cache_path
            )
            started = time.monotonic()
            cache.refresh()
            elapsed = time.monotonic() - started
            self.assertTrue(cache.is_loading())
            release.set()
            deadline = time.monotonic() + 2
            while cache.is_loading() and time.monotonic() < deadline:
                time.sleep(0.01)

        self.assertLess(elapsed, 0.5)
        self.assertFalse(cache.is_loading())

    def test_disk_cache_is_shown_before_the_first_refresh(self) -> None:
        self.cache_path.write_text(
            json.dumps(
                {
                    "url": "https://example.com",
                    "player_name": "Ada",
                    "saved_at": time.time(),
                    "scores": [{"rank": 1, "name": "Cached", "score": 99}],
                    "player": {"rank": 1, "name": "Ada", "score": 99},
                }
            ),
            encoding="utf-8",
        )

        with patch("douda.leaderboard.get_scores") as loader:
            cache = LeaderboardCache(
                "https://example.com", "Ada", cache_path=self.cache_path
            )
            scores, player = cache.snapshot()

        self.assertEqual(scores[0]["name"], "Cached")
        self.assertEqual(player["name"], "Ada")
        loader.assert_not_called()

    def test_successful_refresh_persists_the_cache(self) -> None:
        result = {
            "scores": [{"rank": 1, "name": "Ada", "score": 10}],
            "player": {"rank": 1, "name": "Ada", "score": 10},
        }
        with patch("douda.leaderboard.get_scores", return_value=result):
            cache = LeaderboardCache(
                "https://example.com", "Ada", cache_path=self.cache_path
            )
            cache.refresh(block=True)

        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(data["scores"], result["scores"])
        self.assertEqual(data["player"], result["player"])

    def test_set_player_name_keeps_scores_but_drops_player(self) -> None:
        self.cache_path.write_text(
            json.dumps(
                {
                    "url": "https://example.com",
                    "player_name": "Ada",
                    "saved_at": time.time(),
                    "scores": [{"rank": 1, "name": "Cached", "score": 99}],
                    "player": {"rank": 1, "name": "Ada", "score": 99},
                }
            ),
            encoding="utf-8",
        )
        cache = LeaderboardCache(
            "https://example.com", "Ada", cache_path=self.cache_path
        )

        cache.set_player_name("Bob")
        scores, player = cache.snapshot()

        self.assertEqual(scores[0]["name"], "Cached")
        self.assertIsNone(player)


if __name__ == "__main__":
    unittest.main()
