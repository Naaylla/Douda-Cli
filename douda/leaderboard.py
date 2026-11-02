
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode


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
        with urllib.request.urlopen(request, timeout=5) as response:
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
) -> dict[str, Any]:
    """Fetch leaderboard scores and optionally a player's best rank."""
    query = {"limit": limit, "offset": offset}
    if player_name:
        query["name"] = player_name
    return _request(
        f"{base_url.rstrip('/')}/scores?{urlencode(query)}"
    )
