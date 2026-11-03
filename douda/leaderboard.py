
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlencode

_REQUEST_TIMEOUT = 30


class LeaderboardError(Exception):
    """Raised when the leaderboard cannot be reached or rejects a request."""


def _request(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_response = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            error_response = {}
        finally:
            exc.close()
        if isinstance(error_response, dict) and "error" in error_response:
            raise LeaderboardError(str(error_response["error"])) from exc
        raise LeaderboardError(f"Leaderboard returned HTTP {exc.code}") from exc
    except (
        urllib.error.URLError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise LeaderboardError(f"Could not contact leaderboard: {exc}") from exc

    if not isinstance(result, dict):
        raise LeaderboardError("Leaderboard returned an invalid response.")
    if "error" in result:
        raise LeaderboardError(str(result["error"]))
    return result


def submit_score(base_url: str, name: str, score: int) -> dict[str, Any]:
    """Submit one score and return the server response."""
    return _request(
        f"{base_url.rstrip('/')}/scores",
        {"name": name, "score": score},
    )


def get_scores(
    base_url: str,
    limit: int = 10,
    offset: int = 0,
    player_name: str | None = None,
    score_id: int | None = None,
) -> dict[str, Any]:
    """Fetch leaderboard scores and optionally a player's rank."""
    query = {"limit": limit, "offset": offset}
    if player_name:
        query["name"] = player_name
    if score_id is not None:
        query["score_id"] = score_id
    return _request(
        f"{base_url.rstrip('/')}/scores?{urlencode(query)}"
    )


class LeaderboardCache:
    """Keep a live snapshot of the leaderboard without blocking gameplay.

    Refreshes run on a daemon thread so network I/O never delays the first
    frame or a replay. ``snapshot`` always returns the most recent data.
    """

    def __init__(
        self,
        base_url: str,
        player_name: str,
        limit: int = 3,
        loader: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._base_url = base_url
        self._player_name = player_name
        self._limit = limit
        self._loader = loader or get_scores
        self._lock = threading.Lock()
        self._scores: list[dict[str, object]] = []
        self._player: dict[str, object] | None = None
        self._score_id: int | None = None
        self._loading = False
        self._warned = False

    def focus_score(self, score_id: int) -> None:
        """Show the rank of one submitted score instead of the player's best."""
        with self._lock:
            self._score_id = score_id

    def refresh(self, block: bool = False) -> None:
        if block:
            self._load()
            return
        with self._lock:
            if self._loading:
                return
            self._loading = True
        thread = threading.Thread(target=self._load, daemon=True)
        thread.start()

    def snapshot(self) -> tuple[list[dict[str, object]], dict[str, object] | None]:
        with self._lock:
            return list(self._scores), self._player

    def is_loading(self) -> bool:
        with self._lock:
            return self._loading

    def _load(self) -> None:
        scores = None
        player = None
        with self._lock:
            score_id = self._score_id
        try:
            if score_id is None:
                result = self._loader(
                    self._base_url, self._limit, 0, self._player_name
                )
            else:
                result = self._loader(
                    self._base_url,
                    self._limit,
                    0,
                    self._player_name,
                    score_id=score_id,
                )
            scores = result.get("scores", [])
            player = result.get("player")
        except LeaderboardError as exc:
            if not self._warned:
                print(
                    f"Leaderboard unavailable for this run: {exc}",
                    file=sys.stderr,
                )
                self._warned = True
        finally:
            with self._lock:
                if scores is not None:
                    self._scores = scores
                    self._player = player
                self._loading = False
