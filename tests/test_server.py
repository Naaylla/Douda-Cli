from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from douda.leaderboard import get_scores, submit_score
from douda.server import create_server


class LeaderboardServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.server = create_server(
            host="127.0.0.1",
            port=0,
            db_path=Path(self.temp_dir.name) / "scores.sqlite3",
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp_dir.cleanup()

    def post_score(self, name: str, score: object) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.url}/scores",
            data=json.dumps({"name": name, "score": score}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_scores_are_persisted_and_paginated(self) -> None:
        submit_score(self.url, "Ada", 20)
        submit_score(self.url, "Lin", 50)
        submit_score(self.url, "Sam", 30)
        result = get_scores(self.url, limit=2, offset=1)

        self.assertEqual(result["total"], 3)
        self.assertEqual([entry["name"] for entry in result["scores"]], ["Sam", "Ada"])
        self.assertEqual([entry["rank"] for entry in result["scores"]], [2, 3])

    def test_leaderboard_includes_top_three_and_personal_best_rank(self) -> None:
        submit_score(self.url, "Ada", 10)
        submit_score(self.url, "Lin", 100)
        submit_score(self.url, "Sam", 80)
        submit_score(self.url, "Jo", 50)
        submit_score(self.url, "ada", 20)

        result = get_scores(self.url, limit=3, player_name="Ada")

        self.assertEqual([entry["name"] for entry in result["scores"]], ["Lin", "Sam", "Jo"])
        self.assertEqual(
            result["player"],
            {"name": "ada", "score": 20, "rank": 4},
        )

    def test_personal_rank_is_null_when_player_has_no_scores(self) -> None:
        result = get_scores(self.url, player_name="Unknown")

        self.assertIsNone(result["player"])

    def test_invalid_scores_are_rejected(self) -> None:
        for score in (-1, True, 1.5, "12"):
            with self.subTest(score=score):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.post_score("Ada", score)
                caught.exception.close()
                self.assertEqual(caught.exception.code, 400)

    def test_invalid_page_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{self.url}/scores?limit=101")
        caught.exception.close()
        self.assertEqual(caught.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
