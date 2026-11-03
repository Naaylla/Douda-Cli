
from __future__ import annotations

import argparse
import os
import random
import sys

from douda import terminal
from douda.game import _leaderboard_row, play, wait_for_replay
from douda.leaderboard import (
    LeaderboardCache,
    LeaderboardError,
    get_scores,
    submit_score,
)

DEFAULT_LEADERBOARD_URL = "https://douda-cli.onrender.com"
LEADERBOARD_LIMIT = 7
_QUIT_QUOTES = (
    "You died in a rectangle. Your ancestors are so confused.",
    "The snake has left the chat. It was never invited.",
    "You fought bravely. The wall had more pixels.",
    "Somewhere, a potato believes in you. It is not this potato.",
    "Skill issue?",
    "You were so close. (You were not close.)",
    "The leaderboard called. It said 'who is this'.",
    "You died. The snake is sad. The wall is happy."
)


def _leaderboard_url() -> str:
    return os.environ.get(
        "DOUDA_LEADERBOARD_URL", DEFAULT_LEADERBOARD_URL
    ).rstrip("/")


def _print_quit_quote() -> None:
    quote = random.choice(_QUIT_QUOTES)
    plain = terminal.plain_mode()
    color = terminal.color_enabled(sys.stdout)
    if plain:
        sparkle = "*"
    else:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            "✨".encode(encoding)
            sparkle = "✨"
        except (LookupError, UnicodeEncodeError):
            sparkle = "*"
    print(
        f"{_paint(sparkle, '1;33', color)} "
        f"{_paint(quote, '1;35', color)} "
        f"{_paint(sparkle, '1;33', color)}"
    )


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{color}m{text}\033[0m"


def _box_row(content: str, inner_width: int) -> str:
    return "|" + terminal.pad_visible(content, inner_width) + "|"


def _print_leaderboard(
    url: str, limit: int, offset: int, player_name: str | None
) -> int:
    try:
        result = get_scores(url, limit, offset, player_name)
    except LeaderboardError as exc:
        print(f"Leaderboard error: {exc}", file=sys.stderr)
        print(
            "Start the server with `douda-server` or set DOUDA_LEADERBOARD_URL.",
            file=sys.stderr,
        )
        return 1

    scores = result.get("scores", [])
    player = result.get("player")
    color = terminal.color_enabled(sys.stdout)
    width = 40
    inner_width = width - 2
    border = "+" + "-" * inner_width + "+"
    shown_limit = min(limit, LEADERBOARD_LIMIT)

    print(_paint(border, "36", color))
    title = f"  DOUDA  /  GLOBAL TOP {shown_limit}"
    print(_paint(_box_row(title, inner_width), "1;36", color))
    print(_paint(border, "36", color))

    if not scores:
        print(_paint(_box_row("  No scores yet - go play!", inner_width), "36", color))
    else:
        rank_colors = ("33", "37", "31")
        for index, entry in enumerate(scores[:shown_limit], start=1):
            rank = entry.get("rank", index)
            name = entry.get("name", "Player")
            score = entry.get("score", 0)
            row = _box_row(
                _leaderboard_row(rank, name, score, inner_width), inner_width
            )
            print(_paint(row, rank_colors[min(index - 1, 2)], color))

    player_rank = 0
    if player:
        try:
            player_rank = int(player.get("rank", 0))
        except (TypeError, ValueError):
            player_rank = 0
    if player and player_rank > shown_limit:
        print(_paint(_box_row("...", inner_width), "36", color))
        player_row = _box_row(
            _leaderboard_row(
                player.get("rank", "?"),
                player.get("name", player_name or "You"),
                player.get("score", 0),
                inner_width,
            ),
            inner_width,
        )
        print(_paint(player_row, "1;32", color))

    print(_paint(border, "36", color))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="douda",
        description="Play terminal Snake and climb the shared leaderboard.",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="disable colors and Unicode (ASCII-only mode)",
    )
    subparsers = parser.add_subparsers(dest="command")
    leaderboard_parser = subparsers.add_parser(
        "leaderboard", help="show the top scores and your best rank"
    )
    leaderboard_parser.add_argument("--player", help="show this player's rank")
    leaderboard_parser.add_argument("--limit", type=int, default=LEADERBOARD_LIMIT)
    leaderboard_parser.add_argument("--offset", type=int, default=0)
    leaderboard_parser.add_argument(
        "--plain",
        action="store_true",
        default=argparse.SUPPRESS,
        help="disable colors and Unicode (ASCII-only mode)",
    )
    args = parser.parse_args()
    terminal.configure(getattr(args, "plain", False))

    if args.command == "leaderboard":
        if not 1 <= args.limit <= 100 or args.offset < 0:
            parser.error("--limit must be 1-100 and --offset must be non-negative")
        raise SystemExit(
            _print_leaderboard(
                _leaderboard_url(), args.limit, args.offset, args.player
            )
        )

    leaderboard_url = _leaderboard_url()
    leaderboard = LeaderboardCache(
        leaderboard_url, "", limit=LEADERBOARD_LIMIT, loader=get_scores
    )
    leaderboard.refresh()
    top_scores, player_position = leaderboard.snapshot()
    name: str | None = None

    print("Starting Douda - press WASD or arrow keys to move; Q quits.")
    while True:
        leaderboard.refresh()
        score, ended = play(
            name or "Player",
            top_scores,
            player_position,
            leaderboard=leaderboard,
        )
        if not ended:
            print(f"Quit. Final score: {score}")
            _print_quit_quote()
            return

        print(f"Game over! Final score: {score}")
        if name is None:
            while True:
                try:
                    entered_name = input(
                        "Enter your leaderboard name (1-24 characters): "
                    ).strip()
                except EOFError:
                    entered_name = "Player"
                if entered_name and len(entered_name) <= 24 and all(
                    ord(character) >= 32 and ord(character) != 127
                    for character in entered_name
                ):
                    name = entered_name
                    break
                print(
                    "Name must be 1-24 characters without control characters.",
                    file=sys.stderr,
                )
        assert name is not None
        leaderboard = LeaderboardCache(
            leaderboard_url, name, limit=LEADERBOARD_LIMIT, loader=get_scores
        )
        try:
            submitted = submit_score(leaderboard_url, name, score)
        except LeaderboardError as exc:
            print(f"Could not submit score: {exc}", file=sys.stderr)
            print(
                "The score may have been received, but its submission was not "
                "confirmed. Check the leaderboard before trying to submit it again.",
                file=sys.stderr,
            )
        else:
            score_id = submitted.get("id")
            if isinstance(score_id, int):
                leaderboard.focus_score(score_id)
            print("Score submitted to the shared leaderboard!")
        leaderboard.refresh()
        if not wait_for_replay():
            _print_quit_quote()
            return
        print("Starting another run - press WASD or arrow keys to move; Q quits.")


if __name__ == "__main__":
    main()
