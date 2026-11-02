from __future__ import annotations

import unittest

from douda.game import _board_size, _place_food_on_board, _render


class GameDisplayTests(unittest.TestCase):
    def test_board_fits_terminal_dimensions(self) -> None:
        self.assertEqual(_board_size(columns=42, lines=12), (30, 9))
        self.assertEqual(_board_size(columns=20, lines=30), (18, 14))

    def test_board_fits_very_small_terminal(self) -> None:
        width, height = _board_size(columns=8, lines=6)

        self.assertEqual((width, height), (6, 3))
        self.assertLessEqual(width + 2, 8)
        self.assertLessEqual(height + 3, 6)

    def test_render_uses_square_snake_and_fixed_board(self) -> None:
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

        self.assertEqual(lines[:5], ["+----+", "|    |", "|■■◆ |", "|    |", "+----+"])
        self.assertEqual(len(lines[-1]), 10)

    def test_food_is_inside_resized_board(self) -> None:
        food = _place_food_on_board([(0, 0)], width=8, height=5)

        self.assertIsNotNone(food)
        assert food is not None
        self.assertTrue(0 <= food[0] < 8)
        self.assertTrue(0 <= food[1] < 5)


if __name__ == "__main__":
    unittest.main()
