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

    available_height = max(1, lines - 15)
    return min(WIDTH, max(3, columns - 2)), min(HEIGHT, available_height)


def _movement_delay(score: int, direction: tuple[int, int]) -> float:
    delay = max(0.055, 0.13 - score * 0.0007)
    return delay * 1.5 if direction[1] else delay


def _render(
    snake: list[tuple[int, int]],
    food: tuple[int, int] | None,
    score: int,
    name: str,
    width: int,
    height: int,
    columns: int,
    top_scores: list[dict[str, object]] | None = None,
    top_padding: int = 0,
    color: bool = False,
    player_position: dict[str, object] | None = None,
) -> str:
    def paint(text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "■".encode(encoding)
        snake_glyph = "■"
    except UnicodeEncodeError:
        snake_glyph = "#"
    try:
        "◆".encode(encoding)
        food_glyph = "◆"
    except UnicodeEncodeError:
        food_glyph = "*"

    title_letters = {
        "D": (".__. ", "|   \\", "|   |", "|   /", "|___/"),
        "O": (".---.", "|   |", "|   |", "|   |", "'---'"),
        "U": ("|   |", "|   |", "|   |", "\\   /", "'---'"),
        "A": (".---.", "|   |", "|---|", "|   |", "|   |"),
    }
    title = [
        "  ".join(title_letters[letter][row] for letter in "DOUDA")
        for row in range(5)
    ]
    if columns < len(title[0]):
        title = ["DOUDA"]
    title_width = max(map(len, title))
    header = [
        paint(line.ljust(title_width).center(columns), "1;36")
        for line in title
    ]
    header.append(paint("by Naaylla".center(columns), "2;37"))

    body = set(snake[1:])
    head = snake[0]
    border = "+" + "-" * width + "+"
    board_lines = [paint(border, "36")]
    for y in range(height):
        row = []
        for x in range(width):
            point = (x, y)
            if point == head:
                row.append(paint(snake_glyph, "1;32"))
            elif point in body:
                row.append(paint(snake_glyph, "32"))
            elif point == food:
                row.append(paint(food_glyph, "1;33"))
            else:
                row.append(" ")
        board_lines.append("|" + "".join(row) + "|")
    board_lines.append(paint(border, "36"))
    score_text = f" SCORE  {score:04d} " if width >= 11 else str(score)
    score_line = "|" + score_text.center(width) + "|"
    board_lines.extend(
        [
            paint(border, "36"),
            paint(score_line, "1;33"),
            paint(border, "36"),
            paint(
                " WASD / ARROWS MOVE  Q QUIT "[: width + 2].center(width + 2),
                "2;37",
            ),
        ]
    )

    panel_width = 28
    panel_lines = [
        paint("+" + "-" * (panel_width - 2) + "+", "36"),
        paint("|" + "  LEADERBOARD".center(panel_width - 2) + "|", "1;36"),
        paint("+" + "-" * (panel_width - 2) + "+", "36"),
    ]
    try:
        "♛".encode(encoding)
        crown = "♛"
    except UnicodeEncodeError:
        crown = "*"
    crown_colors = ("33", "37", "31")
    if top_scores:
        for rank, entry in enumerate(top_scores[:3], start=1):
            player_name = str(entry.get("name", "Player"))[:12]
            player_score = str(entry.get("score", 0))[-6:]
            row = f"| {crown}{rank} {player_name:<11} {player_score:>6} |"
            panel_lines.append(paint(row, crown_colors[rank - 1]))
    else:
        panel_lines.append("|  No scores yet            |")
        panel_lines.append("|  Be the first!            |")
    panel_lines.append(paint("+" + "-" * (panel_width - 2) + "+", "36"))
    if player_position and player_position.get("rank", 0) > 3:
        position = f"YOU ARE #{player_position['rank']} · {player_position['score']} pts"
        panel_lines.append(
            paint(
                "|" + f" {position[:panel_width - 4]}".ljust(panel_width - 2) + "|",
                "1;32",
            )
        )
        panel_lines.append(paint("+" + "-" * (panel_width - 2) + "+", "36"))

    show_panel = columns >= width + 2 + 4 + panel_width
    if show_panel:
        content_width = width + 2 + 4 + panel_width
        left_padding = max(0, (columns - content_width) // 2)
        content_lines = []
        for index in range(max(len(board_lines), len(panel_lines))):
            board_line = board_lines[index] if index < len(board_lines) else ""
            panel_line = panel_lines[index] if index < len(panel_lines) else ""
            content_lines.append(
                " " * left_padding
                + board_line.ljust(width + 2)
                + " " * 4
                + panel_line
            )
    else:
        left_padding = max(0, (columns - (width + 2)) // 2)
        content_lines = [" " * left_padding + line for line in board_lines]

    return "\n" * top_padding + "\n".join(header + [""] + content_lines)


def _draw(
    snake: list[tuple[int, int]],
    food: tuple[int, int] | None,
    score: int,
    name: str,
    width: int,
    height: int,
    columns: int,
    top_scores: list[dict[str, object]] | None,
    top_padding: int,
    color: bool,
    player_position: dict[str, object] | None,
) -> None:
    print(
        "\033[H\033[J"
        + _render(
            snake,
            food,
            score,
            name,
            width,
            height,
            columns,
            top_scores,
            top_padding,
            color,
            player_position,
        ),
        end="",
    )
    sys.stdout.flush()


def play(
    name: str,
    top_scores: list[dict[str, object]] | None = None,
    player_position: dict[str, object] | None = None,
) -> tuple[int, bool]:
    """Play one game; return (score, whether the run ended by winning/dying)."""
    columns, terminal_lines = shutil.get_terminal_size(fallback=(80, 24))
    width, height = _board_size(columns, terminal_lines)
    top_padding = min(2, max(0, terminal_lines - height - 5))
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
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
                _draw(
                    snake,
                    food,
                    score,
                    name,
                    width,
                    height,
                    columns,
                    top_scores,
                    top_padding,
                    color,
                    player_position,
                )
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

                time.sleep(_movement_delay(score, direction))
    finally:
        print("\033[?25h")

    return score, ended


def wait_for_replay() -> bool:
    print("Do you want to replay? Press R to replay or Q to quit.")
    with Keyboard() as keyboard:
        while True:
            key = keyboard.read()
            if key == "r":
                return True
            if key == "q":
                return False
            time.sleep(0.05)
