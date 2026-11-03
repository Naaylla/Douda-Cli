from __future__ import annotations

import os
import io
import threading
import time
import unittest
from unittest.mock import patch

from douda.cli import (
    DEFAULT_LEADERBOARD_URL,
    LEADERBOARD_LIMIT,
    _QUIT_QUOTES,
    _leaderboard_url,
    _print_leaderboard,
    _print_quit_quote,
    main,
)
from douda.leaderboard import LeaderboardCache
from douda.terminal import reset, visible_width


class LeaderboardUrlTests(unittest.TestCase):
    def test_game_asks_for_name_only_after_a_loss_and_reuses_it_on_replay(self) -> None:
        reset()
        self.addCleanup(reset)
        with patch("douda.cli.sys.argv", ["douda"]), patch(
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

        prompt.assert_called_once()
        submit.assert_called_once_with(
            "https://douda-cli.onrender.com", "Ada", 10
        )
        self.assertEqual(
            [call.args[0] for call in play.call_args_list], ["Player", "Ada"]
        )
        self.assertEqual(cache_class.call_args.args[1], "Ada")
        cache_class.return_value.focus_score.assert_called_once_with(12)

    def test_leaderboard_does_not_assume_a_player_name(self) -> None:
        reset()
        self.addCleanup(reset)
        with patch("douda.cli.sys.argv", ["douda", "leaderboard"]), patch(
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

        with patch("douda.cli.get_scores", return_value=result), patch(
            "douda.cli.sys.stdout", output
        ):
            status = _print_leaderboard(
                "https://example.com", LEADERBOARD_LIMIT, 0, "Ada"
            )

        rendered = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("GLOBAL TOP 7", rendered)
        self.assertIn("1. Ada", rendered)
        for rank, name in enumerate(("Jo", "Kim", "Lee", "Max"), start=4):
            self.assertIn(f"{rank}. {name}", rendered)
        self.assertIn("17. Ada", rendered)
        self.assertIn("...", rendered)
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
        self.assertIn("...", rendered)
        self.assertEqual(
            {visible_width(line) for line in rendered.splitlines()},
            {40},
        )


class LeaderboardCacheTests(unittest.TestCase):
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
            cache = LeaderboardCache("https://example.com", "Ada")
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
            cache = LeaderboardCache("https://example.com", "Ada")
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


if __name__ == "__main__":
    unittest.main()
