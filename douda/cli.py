
from __future__ import annotations

import argparse
import os
import sys

from douda.game import play
from douda.leaderboard import LeaderboardError, get_scores, submit_score


def _leaderboard_url() -> str:
    return os.environ.get(
        "DOUDA_LEADERBOARD_URL", "http://127.0.0.1:8765"
    ).rstrip("/")


def _print_leaderboard(url: str, limit: int, offset: int) -> int:
    try:
        result = get_scores(url, limit, offset)
    except LeaderboardError as exc:
        print(f"Leaderboard error: {exc}", file=sys.stderr)
        print(
            "Start the server with `douda-server` or set DOUDA_LEADERBOARD_URL.",
            file=sys.stderr,
        )
        return 1

    scores = result.get("scores", [])
    print(f"Douda Leaderboard — {result.get('total', 0)} total scores")
    if not scores:
        print("No scores on this page yet.")
        return 0
    print(f"{'Rank':>5}  {'Score':>7}  Player")
    for entry in scores:
        print(f"{entry['rank']:>5}  {entry['score']:>7}  {entry['name']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="douda",
        description="Play terminal Snake and climb the shared leaderboard.",
    )
    parser.add_argument("--name", help="leaderboard name (1-24 characters)")
    subparsers = parser.add_subparsers(dest="command")
    leaderboard_parser = subparsers.add_parser(
        "leaderboard", help="show a page of shared scores"
    )
    leaderboard_parser.add_argument("--limit", type=int, default=10)
    leaderboard_parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    if args.command == "leaderboard":
        if not 1 <= args.limit <= 100 or args.offset < 0:
            parser.error("--limit must be 1-100 and --offset must be non-negative")
        raise SystemExit(_print_leaderboard(_leaderboard_url(), args.limit, args.offset))

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

    print("Starting Douda — press WASD or arrow keys to move; Q quits.")
    score, ended = play(name)
    if not ended:
        print(f"Quit. Final score: {score}")
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
        return
    print("Score submitted to the shared leaderboard!")


if __name__ == "__main__":
    main()
