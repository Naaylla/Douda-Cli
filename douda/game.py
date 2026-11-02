from __future__ import annotations

import os
import random
import select
import shutil
import sys
import time

WIDTH = 30
HEIGHT = 14
_DIRECTIONS = {
    "w": (0, -1),
    "a": (-1, 0),
    "s": (0, 1),
    "d": (1, 0),
    "\x1b[A": (0, -1),
    "\x1b[D": (-1, 0),
    "\x1b[B": (0, 1),
    "\x1b[C": (1, 0),
}


class Keyboard:
    """Read single key presses without waiting for Enter."""

    def __init__(self) -> None:
        self._terminal_settings: list[object] | None = None
        self._stream = None

    def __enter__(self) -> Keyboard:
        if os.name != "nt":
            import termios
            import tty

            self._stream = sys.stdin
            self._terminal_settings = termios.tcgetattr(self._stream.fileno())
            tty.setcbreak(self._stream.fileno())
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._terminal_settings is not None and self._stream is not None:
            import termios

            termios.tcsetattr(
                self._stream.fileno(), termios.TCSADRAIN, self._terminal_settings
            )

    def read(self) -> str | None:
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            key = msvcrt.getch()
            if key in (b"\x00", b"\xe0") and msvcrt.kbhit():
                return {
                    b"H": "\x1b[A",
                    b"K": "\x1b[D",
                    b"P": "\x1b[B",
                    b"M": "\x1b[C",
                }.get(msvcrt.getch())
            return key.decode("utf-8", errors="ignore").lower()

        if self._stream is None:
            return None
        readable, _, _ = select.select([self._stream], [], [], 0)
        if not readable:
            return None
        key = os.read(self._stream.fileno(), 1).decode("utf-8", errors="ignore")
        if key != "\x1b":
            return key.lower()
        sequence = key
        for _ in range(2):
            readable, _, _ = select.select([self._stream], [], [], 0.01)
            if not readable:
                break
            sequence += os.read(self._stream.fileno(), 1).decode(
                "utf-8", errors="ignore"
            )
        return sequence


def _place_food_on_board(
    snake: list[tuple[int, int]], width: int, height: int
) -> tuple[int, int] | None:
    occupied = set(snake)
    available = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if (x, y) not in occupied
    ]
    return random.choice(available) if available else None


def _board_size(columns: int | None = None, lines: int | None = None) -> tuple[int, int]:
    if columns is None or lines is None:
        terminal = shutil.get_terminal_size(fallback=(80, 24))
        columns = terminal.columns if columns is None else columns
        lines = terminal.lines if lines is None else lines

    return min(WIDTH, max(3, columns - 2)), min(HEIGHT, max(1, lines - 3))


def _render(
    snake: list[tuple[int, int]],
    food: tuple[int, int] | None,
    score: int,
    name: str,
    width: int,
    height: int,
    columns: int,
) -> str:
    body = set(snake[1:])
    head = snake[0]
    border = "+" + "-" * width + "+"
    lines = [border]
    for y in range(height):
        row = []
        for x in range(width):
            point = (x, y)
            if point == head:
                row.append("■")
            elif point in body:
                row.append("■")
            elif point == food:
                row.append("◆")
            else:
                row.append(" ")
        lines.append("|" + "".join(row) + "|")
    lines.append(border)
    status = f"{name[:8]} Score:{score} WASD/Q"
    lines.append(status[:columns])
    return "\n".join(lines)


def _draw(
    snake: list[tuple[int, int]],
    food: tuple[int, int] | None,
    score: int,
    name: str,
    width: int,
    height: int,
    columns: int,
) -> None:
    print(
        "\033[2J\033[H" + _render(snake, food, score, name, width, height, columns),
        end="",
    )
    sys.stdout.flush()


def play(name: str) -> tuple[int, bool]:
    """Play one game; return (score, whether the run ended by winning/dying)."""
    columns, terminal_lines = shutil.get_terminal_size(fallback=(80, 24))
    width, height = _board_size(columns, terminal_lines)
    snake_length = min(3, width - 1)
    start_x = min(width // 2, width - 2)
    snake = [(start_x - index, height // 2) for index in range(snake_length)]
    direction = (1, 0)
    food = _place_food_on_board(snake, width, height)
    score = 0
    ended = False

    print("\033[?25l", end="")
    try:
        with Keyboard() as keyboard:
            while True:
                _draw(snake, food, score, name, width, height, columns)
                key = keyboard.read()
                if key == "q":
                    break
                if key in _DIRECTIONS:
                    candidate = _DIRECTIONS[key]
                    if candidate != (-direction[0], -direction[1]):
                        direction = candidate

                next_head = (snake[0][0] + direction[0], snake[0][1] + direction[1])
                growing = next_head == food
                collision_body = snake if growing else snake[:-1]
                if (
                    not 0 <= next_head[0] < width
                    or not 0 <= next_head[1] < height
                    or next_head in collision_body
                ):
                    ended = True
                    break

                snake.insert(0, next_head)
                if growing:
                    score += 10
                    food = _place_food_on_board(snake, width, height)
                    if food is None:
                        ended = True
                        break
                else:
                    snake.pop()

                time.sleep(max(0.055, 0.13 - score * 0.0007))
    finally:
        print("\033[?25h")

    return score, ended
