from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from douda.cli import DEFAULT_LEADERBOARD_URL, _leaderboard_url


class LeaderboardUrlTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
