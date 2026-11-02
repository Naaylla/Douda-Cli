
from __future__ import annotations

import argparse
import os
import random
import sys

from douda.game import play, wait_for_replay
from douda.leaderboard import LeaderboardError, get_scores, submit_score

DEFAULT_LEADERBOARD_URL = "https://douda-cli.onrender.com"
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
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✨".encode(encoding)
        sparkle = "✨"
    except UnicodeEncodeError:
        sparkle = "*"
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    print(
        f"{_paint(sparkle, '1;33', color)} "
        f"{_paint(quote, '1;35', color)} "
        f"{_paint(sparkle, '1;33', color)}"
    )


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{color}m{text}\033[0m"


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
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    width = 40
    border = "+" + "-" * (width - 2) + "+"

    print(_paint(border, "36", color))
    title = f"  DOUDA  /  GLOBAL TOP {limit}"
    print(_paint("|" + title.center(width - 2) + "|", "1;36", color))
    print(_paint(border, "36", color))

    if not scores:
        print("|" + "  No scores yet — go play!".ljust(width - 2) + "|")
    else:
        for index, entry in enumerate(scores, start=1):
            rank = entry.get("rank", index)
            name = str(entry.get("name", "Player"))[:18]
            score = entry.get("score", 0)
            row = f"|  #{rank:<2} {name:<18} {score:>8} pts  |"
            color_code = ("33", "37", "31")[min(index - 1, 2)]
            print(_paint(row, color_code, color))

    print(_paint(border, "36", color))
    if player_name:
        if player:
            rank = player["rank"]
            best_score = player["score"]
            personal = f"|  YOUR BEST   #{rank}  ·  {best_score} pts"
        else:
            personal = f"|  {player_name[:12]}: no score yet — go play"
        print(_paint(personal.ljust(width - 1) + "|", "1;32", color))
        print(_paint(border, "36", color))
    else:
        print(f"Set DOUDA_PLAYER or use `douda leaderboard --player NAME` for your rank.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="douda",
        description="Play terminal Snake and climb the shared leaderboard.",
    )
    parser.add_argument("--name", help="leaderboard name (1-24 characters)")
    subparsers = parser.add_subparsers(dest="command")
    leaderboard_parser = subparsers.add_parser(
        "leaderboard", help="show the top scores and your best rank"
    )
    leaderboard_parser.add_argument("--player", help="your leaderboard name")
    leaderboard_parser.add_argument("--limit", type=int, default=3)
    leaderboard_parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    if args.command == "leaderboard":
        if not 1 <= args.limit <= 100 or args.offset < 0:
            parser.error("--limit must be 1-100 and --offset must be non-negative")
        player_name = args.player or os.environ.get("DOUDA_PLAYER")
        if not player_name:
            try:
                player_name = input("Your leaderboard name: ")
            except EOFError:
                player_name = None
        if player_name:
            player_name = player_name.strip()
            if (
                not player_name
                or len(player_name) > 24
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in player_name
                )
            ):
                parser.error(
                    "player name must be 1-24 characters without control characters"
                )
        raise SystemExit(
            _print_leaderboard(
                _leaderboard_url(), args.limit, args.offset, player_name
            )
        )

    name = args.name or os.environ.get("DOUDA_PLAYER")
    if not name:
        try:
            name = input("Player name for the leaderboard (max 24 characters): ")
        except EOFError:
            name = "Player"
    name = name.strip() or "Player"
    if len(name) > 24 or any(
        ord(character) < 32 or ord(character) == 127 for character in name
    ):
        parser.error("player name must be 1-24 characters without control characters")

    try:
        leaderboard = get_scores(
            _leaderboard_url(), limit=3, player_name=name
        )
        top_scores = leaderboard.get("scores", [])
        player_position = leaderboard.get("player")
    except LeaderboardError as exc:
        print(f"Leaderboard unavailable for this run: {exc}", file=sys.stderr)
        top_scores = []
        player_position = None

    print("Starting Douda — press WASD or arrow keys to move; Q quits.")
    while True:
        score, ended = play(name, top_scores, player_position)
        if not ended:
            print(f"Quit. Final score: {score}")
            _print_quit_quote()
            return

        print(f"Game over! Final score: {score}")
        try:
            submit_score(_leaderboard_url(), name, score)
        except LeaderboardError as exc:
            print(f"Could not submit score: {exc}", file=sys.stderr)
            print(
                "Your run is over, but the score was not saved. "
                "Start the server or check DOUDA_LEADERBOARD_URL.",
                file=sys.stderr,
            )
        else:
            print("Score submitted to the shared leaderboard!")
        if not wait_for_replay():
            _print_quit_quote()
            return
        print("Starting another run — press WASD or arrow keys to move; Q quits.")


if __name__ == "__main__":
    main()
