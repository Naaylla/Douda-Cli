from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

_REQUEST_TIMEOUT = 8
_SUBMIT_TIMEOUT = 5
_RETRIES = 1
_RETRY_DELAY = 0.25
_CACHE_TTL = 60 * 60 * 24 * 7


class LeaderboardError(Exception):
    """Raised when the leaderboard cannot be reached or rejects a request."""


def _cache_path() -> Path:
    if os.name == "nt":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or Path.home()
        )
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "douda" / "leaderboard-cache.json"


def _parse_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise LeaderboardError("Leaderboard returned an invalid response.")
    if "error" in result:
        raise LeaderboardError(str(result["error"]))
    return result


def _request(
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = _REQUEST_TIMEOUT,
    retries: int = _RETRIES,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            return _parse_result(result)
        except urllib.error.HTTPError as exc:
            try:
                error_response = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                error_response = {}
            finally:
                exc.close()
            message = (
                str(error_response["error"])
                if isinstance(error_response, dict) and "error" in error_response
                else f"Leaderboard returned HTTP {exc.code}"
            )
            if exc.code >= 500 and attempt < retries:
                last_error = LeaderboardError(message)
                time.sleep(_RETRY_DELAY * (attempt + 1))
                continue
            raise LeaderboardError(message) from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(_RETRY_DELAY * (attempt + 1))

    raise LeaderboardError(
        f"Could not contact leaderboard: {last_error}"
    ) from last_error


def submit_score(base_url: str, name: str, score: int) -> dict[str, Any]:
    """Submit one score and return the server response."""
    return _request(
        f"{base_url.rstrip('/')}/scores",
        {"name": name, "score": score},
        timeout=_SUBMIT_TIMEOUT,
    )


def get_scores(
    base_url: str,
    limit: int = 10,
    offset: int = 0,
    player_name: str | None = None,
    score_id: int | None = None,
    include_total: bool = False,
) -> dict[str, Any]:
    """Fetch leaderboard scores and optionally a player's rank."""
    query = {"limit": limit, "offset": offset}
    if player_name:
        query["name"] = player_name
    if score_id is not None:
        query["score_id"] = score_id
    if include_total:
        query["include_total"] = 1
    return _request(
        f"{base_url.rstrip('/')}/scores?{urlencode(query)}"
    )


class LeaderboardCache:
    """Keep a live snapshot of the leaderboard without blocking gameplay.

    Refreshes run on a daemon thread so network I/O never delays the first
    frame or a replay. ``snapshot`` always returns the most recent data, and
    the last successful snapshot is persisted to disk so a cold start still
    shows real scores instantly.
    """

    def __init__(
        self,
        base_url: str,
        player_name: str,
        limit: int = 5,
        loader: Callable[..., dict[str, Any]] | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._player_name = player_name
        self._limit = limit
        self._loader = loader or get_scores
        self._cache_path = cache_path or _cache_path()
        self._lock = threading.Lock()
        self._scores: list[dict[str, object]] = []
        self._player: dict[str, object] | None = None
        self._score_id: int | None = None
        self._loading = False
        self._warned = False
        self._scores, self._player = self._read_cache()

    def set_player_name(self, player_name: str) -> None:
        """Update the player without discarding the cached top scores."""
        with self._lock:
            if self._player_name == player_name:
                return
            self._player_name = player_name
            self._player = None

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

    def _read_cache(
        self,
    ) -> tuple[list[dict[str, object]], dict[str, object] | None]:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [], None
        if not isinstance(data, dict) or data.get("url") != self._base_url:
            return [], None
        try:
            saved_at = float(data.get("saved_at", 0))
        except (TypeError, ValueError):
            saved_at = 0.0
        if saved_at and time.time() - saved_at > _CACHE_TTL:
            return [], None
        scores = data.get("scores")
        if not isinstance(scores, list):
            return [], None
        scores = [entry for entry in scores if isinstance(entry, dict)]
        player = data.get("player")
        if (
            not isinstance(player, dict)
            or data.get("player_name") != self._player_name
        ):
            player = None
        return scores, player

    def _write_cache(
        self,
        scores: list[dict[str, object]],
        player: dict[str, object] | None,
    ) -> None:
        data = {
            "url": self._base_url,
            "player_name": self._player_name,
            "saved_at": time.time(),
            "scores": scores,
            "player": player,
        }
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                dir=self._cache_path.parent,
                prefix=".leaderboard-",
                suffix=".tmp",
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False)
                os.replace(temp_name, self._cache_path)
            except BaseException:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        except OSError:
            pass

    def _load(self) -> None:
        scores = None
        player = None
        with self._lock:
            score_id = self._score_id
            player_name = self._player_name
        try:
            if score_id is None:
                result = self._loader(
                    self._base_url, self._limit, 0, player_name
                )
            else:
                result = self._loader(
                    self._base_url,
                    self._limit,
                    0,
                    player_name,
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
                    self._player = (
                        player if self._player_name == player_name else None
                    )
                self._loading = False
        if scores is not None:
            with self._lock:
                cache_player = (
                    player if self._player_name == player_name else None
                )
            self._write_cache(scores, cache_player)
