from __future__ import annotations

import os
import io
import unittest
from unittest.mock import patch

from douda.cli import (
    DEFAULT_LEADERBOARD_URL,
    _QUIT_QUOTES,
    _leaderboard_url,
    _print_leaderboard,
    _print_quit_quote,
)


class LeaderboardUrlTests(unittest.TestCase):
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
            ],
            "player": {"rank": 17, "score": 20},
        }
        output = io.StringIO()

        with patch("douda.cli.get_scores", return_value=result), patch(
            "douda.cli.sys.stdout", output
        ):
            status = _print_leaderboard("https://example.com", 3, 0, "Ada")

        rendered = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("GLOBAL TOP 3", rendered)
        self.assertIn("#1  Ada", rendered)
        self.assertIn("YOUR BEST   #17  ·  20 pts", rendered)


if __name__ == "__main__":
    unittest.main()
