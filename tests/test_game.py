from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from douda.game import (
    _DIRECTIONS,
    _board_size,
    _movement_delay,
    _place_food_on_board,
    _render,
    wait_for_replay,
)


class GameDisplayTests(unittest.TestCase):
    def test_board_fits_terminal_dimensions(self) -> None:
        self.assertEqual(_board_size(columns=42, lines=12), (30, 1))
        self.assertEqual(_board_size(columns=20, lines=30), (18, 14))

    def test_board_fits_very_small_terminal(self) -> None:
        width, height = _board_size(columns=8, lines=6)

        self.assertEqual((width, height), (6, 1))
        self.assertLessEqual(width + 2, 8)
        self.assertLessEqual(height + 3, 6)

    def test_vertical_movement_uses_moderate_speed_compensation(self) -> None:
        horizontal_delay = _movement_delay(score=0, direction=(1, 0))
        vertical_delay = _movement_delay(score=0, direction=(0, 1))

        self.assertEqual(horizontal_delay, 0.13)
        self.assertAlmostEqual(vertical_delay, horizontal_delay * 1.5)

    def test_render_uses_square_snake_and_fixed_board(self) -> None:
        with patch("douda.game.sys.stdout", io.StringIO()):
            frame = _render(
                snake=[(1, 1), (0, 1)],
                food=(2, 1),
                score=10,
                name="Player",
                width=4,
                height=3,
                columns=10,
            )
        lines = frame.splitlines()

        self.assertIn("DOUDA", frame)
        self.assertIn("by Naaylla", frame)
        self.assertEqual(lines[:2], ["  DOUDA   ", "by Naaylla"])
        self.assertEqual(len({len(line) for line in lines[:2]}), 1)
        board_start = lines.index("  +----+")
        self.assertEqual(
            lines[board_start : board_start + 5],
            ["  +----+", "  |    |", "  |■■◆ |", "  |    |", "  +----+"],
        )
        self.assertLessEqual(len(lines[-1]), 10)

    def test_title_uses_hollow_ascii_lettering(self) -> None:
        frame = _render(
            snake=[(1, 1)],
            food=(2, 1),
            score=0,
            name="Player",
            width=30,
            height=3,
            columns=80,
        )

        self.assertIn("|---|", frame)
        self.assertIn("|___/", frame)
        self.assertNotIn("#", frame.split("by Naaylla", maxsplit=1)[0])

    def test_wasd_and_arrow_keys_are_supported(self) -> None:
        self.assertEqual(_DIRECTIONS["w"], _DIRECTIONS["\x1b[A"])
        self.assertEqual(_DIRECTIONS["a"], _DIRECTIONS["\x1b[D"])
        self.assertEqual(_DIRECTIONS["s"], _DIRECTIONS["\x1b[B"])
        self.assertEqual(_DIRECTIONS["d"], _DIRECTIONS["\x1b[C"])

        frame = _render(
            snake=[(1, 1)],
            food=(2, 1),
            score=0,
            name="Player",
            width=30,
            height=3,
            columns=80,
        )
        self.assertIn("WASD / ARROWS MOVE", frame)

    def test_r_replays_and_q_exits_after_game_over(self) -> None:
        class FakeKeyboard:
            def __init__(self, keys: list[str | None]) -> None:
                self.keys = iter(keys)

            def __enter__(self) -> FakeKeyboard:
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def read(self) -> str | None:
                return next(self.keys)

        output = io.StringIO()
        with redirect_stdout(output):
            with patch("douda.game.Keyboard", return_value=FakeKeyboard([None, "r"])):
                with patch("douda.game.time.sleep"):
                    self.assertTrue(wait_for_replay())

        self.assertIn("Do you want to replay?", output.getvalue())

        with redirect_stdout(io.StringIO()):
            with patch("douda.game.Keyboard", return_value=FakeKeyboard(["q"])):
                self.assertFalse(wait_for_replay())

    def test_render_places_colored_top_three_beside_board(self) -> None:
        with patch("douda.game.sys.stdout", SimpleNamespace(encoding="utf-8")):
            frame = _render(
                snake=[(1, 1)],
                food=(2, 1),
                score=20,
                name="Player",
                width=8,
                height=3,
                columns=80,
                top_scores=[
                    {"rank": 1, "name": "Ada", "score": 90},
                    {"rank": 2, "name": "Lin", "score": 80},
                    {"rank": 3, "name": "Sam", "score": 70},
                ],
                top_padding=2,
                color=True,
            )

        self.assertTrue(frame.startswith("\n\n"))
        self.assertIn("|   |", frame)
        self.assertIn("by Naaylla", frame)
        self.assertIn("LEADERBOARD", frame)
        self.assertIn("Ada", frame)
        self.assertIn("♛", frame)
        self.assertIn("\033[1;32m", frame)
        self.assertIn("\033[33m| ♛1", frame)

        title_lines = [
            line.replace("\033[1;36m", "").replace("\033[0m", "")
            for line in frame.splitlines()[2:7]
        ]
        self.assertEqual(len({len(line) for line in title_lines}), 1)

    def test_sidebar_shows_position_below_top_three(self) -> None:
        frame = _render(
            snake=[(1, 1)],
            food=(2, 1),
            score=20,
            name="Player",
            width=8,
            height=3,
            columns=80,
            top_scores=[
                {"rank": 1, "name": "Ada", "score": 90},
                {"rank": 2, "name": "Lin", "score": 80},
                {"rank": 3, "name": "Sam", "score": 70},
            ],
            player_position={"rank": 3000, "score": 20},
        )

        self.assertIn("YOU ARE #3000 · 20 pts", frame)

    def test_sidebar_omits_personal_position_for_top_three_player(self) -> None:
        frame = _render(
            snake=[(1, 1)],
            food=(2, 1),
            score=90,
            name="Ada",
            width=8,
            height=3,
            columns=80,
            top_scores=[{"rank": 1, "name": "Ada", "score": 90}],
            player_position={"rank": 1, "score": 90},
        )

        self.assertNotIn("YOUR POSITION", frame)

    def test_render_hides_sidebar_when_terminal_is_narrow(self) -> None:
        frame = _render(
            snake=[(1, 1)],
            food=(2, 1),
            score=0,
            name="Player",
            width=8,
            height=3,
            columns=20,
            top_scores=[{"name": "Ada", "score": 90}],
        )

        self.assertNotIn("LEADERBOARD", frame)

    def test_food_is_inside_resized_board(self) -> None:
        food = _place_food_on_board([(0, 0)], width=8, height=5)

        self.assertIsNotNone(food)
        assert food is not None
        self.assertTrue(0 <= food[0] < 8)
        self.assertTrue(0 <= food[1] < 5)


if __name__ == "__main__":
    unittest.main()
