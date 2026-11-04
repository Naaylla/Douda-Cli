from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlsplit

from psycopg_pool import ConnectionPool
from dotenv import load_dotenv


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            score INTEGER NOT NULL CHECK (score >= 0),
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS scores_order ON scores(score DESC, id ASC)"
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS scores_player
        ON scores(lower(name), score DESC, id ASC)
        """
    )
    return connection


class LeaderboardStore:
    def __init__(self, db_path: Path, database_url: str | None) -> None:
        self._db_path = db_path
        self._pool = (
            ConnectionPool(conninfo=database_url, min_size=1, max_size=10)
            if database_url
            else None
        )
        self.initialize()

    def initialize(self) -> None:
        if self._pool is None:
            with _database(self._db_path):
                pass
            return

        with self._pool.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS douda_scores (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK (score >= 0),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS douda_scores_order
                ON douda_scores(score DESC, id ASC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS douda_scores_player
                ON douda_scores(lower(name), score DESC, id ASC)
                """
            )

    def page(
        self,
        limit: int,
        offset: int,
        player_name: str | None = None,
        score_id: int | None = None,
        include_total: bool = False,
    ) -> tuple[int | None, list[dict[str, object]], dict[str, object] | None]:
        if self._pool is None:
            with _database(self._db_path) as connection:
                total = None
                if include_total:
                    total = connection.execute(
                        "SELECT COUNT(*) FROM scores"
                    ).fetchone()[0]
                rows = connection.execute(
                    """
                    SELECT name, score, created_at
                    FROM scores
                    ORDER BY score DESC, id ASC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
                player_row = None
                if score_id is not None:
                    player_row = self._rank_for_score_sqlite(connection, score_id)
                elif player_name:
                    player_row = self._rank_for_name_sqlite(connection, player_name)
            return total, [
                {
                    "rank": offset + index + 1,
                    "name": row["name"],
                    "score": row["score"],
                    "created_at": row["created_at"],
                }
                for index, row in enumerate(rows)
            ], player_row

        with self._pool.connection() as connection:
            total = None
            if include_total:
                total = connection.execute(
                    "SELECT COUNT(*) FROM douda_scores"
                ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT name, score, created_at
                FROM douda_scores
                ORDER BY score DESC, id ASC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()
            player_row = None
            if score_id is not None:
                player_row = self._rank_for_score_postgres(connection, score_id)
            elif player_name:
                player_row = self._rank_for_name_postgres(connection, player_name)
        return (
            total,
            [
                {
                    "rank": offset + index + 1,
                    "name": row[0],
                    "score": row[1],
                    "created_at": row[2].isoformat(),
                }
                for index, row in enumerate(rows)
            ],
            player_row,
        )

    @staticmethod
    def _rank_for_score_sqlite(
        connection: sqlite3.Connection, score_id: int
    ) -> dict[str, object] | None:
        row = connection.execute(
            "SELECT name, score, id FROM scores WHERE id = ? LIMIT 1",
            (score_id,),
        ).fetchone()
        if row is None:
            return None
        rank = connection.execute(
            """
            SELECT COUNT(*) + 1
            FROM scores
            WHERE score > ? OR (score = ? AND id < ?)
            """,
            (row["score"], row["score"], row["id"]),
        ).fetchone()[0]
        return {"name": row["name"], "score": row["score"], "rank": rank}

    @staticmethod
    def _rank_for_name_sqlite(
        connection: sqlite3.Connection, player_name: str
    ) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT name, score, id
            FROM scores
            WHERE lower(name) = lower(?)
            ORDER BY score DESC, id ASC
            LIMIT 1
            """,
            (player_name,),
        ).fetchone()
        if row is None:
            return None
        rank = connection.execute(
            """
            SELECT COUNT(*) + 1
            FROM scores
            WHERE score > ? OR (score = ? AND id < ?)
            """,
            (row["score"], row["score"], row["id"]),
        ).fetchone()[0]
        return {"name": row["name"], "score": row["score"], "rank": rank}

    @staticmethod
    def _rank_for_score_postgres(
        connection: Any, score_id: int
    ) -> dict[str, object] | None:
        row = connection.execute(
            "SELECT name, score, id FROM douda_scores WHERE id = %s LIMIT 1",
            (score_id,),
        ).fetchone()
        if row is None:
            return None
        rank = connection.execute(
            """
            SELECT COUNT(*) + 1
            FROM douda_scores
            WHERE score > %s OR (score = %s AND id < %s)
            """,
            (row[1], row[1], row[2]),
        ).fetchone()[0]
        return {"name": row[0], "score": row[1], "rank": rank}

    @staticmethod
    def _rank_for_name_postgres(
        connection: Any, player_name: str
    ) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT name, score, id
            FROM douda_scores
            WHERE lower(name) = lower(%s)
            ORDER BY score DESC, id ASC
            LIMIT 1
            """,
            (player_name,),
        ).fetchone()
        if row is None:
            return None
        rank = connection.execute(
            """
            SELECT COUNT(*) + 1
            FROM douda_scores
            WHERE score > %s OR (score = %s AND id < %s)
            """,
            (row[1], row[1], row[2]),
        ).fetchone()[0]
        return {"name": row[0], "score": row[1], "rank": rank}

    def insert(self, name: str, score: int) -> int:
        if self._pool is None:
            with _database(self._db_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO scores (name, score) VALUES (?, ?)",
                    (name, score),
                )
                return int(cursor.lastrowid)

        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO douda_scores (name, score)
                VALUES (%s, %s)
                RETURNING id
                """,
                (name, score),
            ).fetchone()
        return int(row[0])

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()


@contextmanager
def _database(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str | Path = "douda-leaderboard.sqlite3",
    database_url: str | None = None,
) -> ThreadingHTTPServer:
    """Create an HTTP server backed by Postgres or a local SQLite file."""
    path = Path(db_path).expanduser().resolve()
    store = LeaderboardStore(path, database_url or os.environ.get("DATABASE_URL"))

    class LeaderboardHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send_json(
            self,
            status: int,
            payload: dict[str, object],
            *,
            close: bool = False,
        ) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if parsed.path != "/scores":
                self._send_json(404, {"error": "Not found"})
                return

            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["10"])[0])
                offset = int(query.get("offset", ["0"])[0])
            except ValueError:
                self._send_json(400, {"error": "limit and offset must be integers"})
                return
            if not 1 <= limit <= 100 or offset < 0:
                self._send_json(
                    400,
                    {"error": "limit must be 1-100 and offset must be non-negative"},
                )
                return

            player_name = query.get("name", [None])[0]
            if player_name is not None:
                player_name = player_name.strip()
                if (
                    not player_name
                    or len(player_name) > 24
                    or any(
                        ord(character) < 32 or ord(character) == 127
                        for character in player_name
                    )
                ):
                    self._send_json(
                        400,
                        {"error": "name must be 1-24 characters without control characters"},
                    )
                    return

            score_id: int | None = None
            raw_score_id = query.get("score_id", [None])[0]
            if raw_score_id is not None:
                try:
                    score_id = int(raw_score_id)
                except ValueError:
                    self._send_json(400, {"error": "score_id must be an integer"})
                    return
                if score_id < 1:
                    self._send_json(400, {"error": "score_id must be positive"})
                    return

            include_total = query.get("include_total", ["0"])[0].lower() in (
                "1",
                "true",
                "yes",
            )
            total, scores, player = store.page(
                limit, offset, player_name, score_id, include_total
            )
            self._send_json(
                200,
                {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "scores": scores,
                    "player": player,
                },
            )

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/scores":
                self._send_json(404, {"error": "Not found"}, close=True)
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(
                    400, {"error": "Invalid Content-Length"}, close=True
                )
                return
            if not 0 < content_length <= 4096:
                self._send_json(
                    400,
                    {"error": "Request body must be 1-4096 bytes"},
                    close=True,
                )
                return

            try:
                payload = json.loads(self.rfile.read(content_length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"error": "Request body must be valid JSON"})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "Request body must be a JSON object"})
                return

            name = payload.get("name")
            score = payload.get("score")
            if not isinstance(name, str):
                self._send_json(400, {"error": "name must be a string"})
                return
            name = name.strip()
            if (
                not name
                or len(name) > 24
                or any(ord(character) < 32 or ord(character) == 127 for character in name)
            ):
                self._send_json(
                    400,
                    {"error": "name must be 1-24 characters without control characters"},
                )
                return
            if (
                isinstance(score, bool)
                or not isinstance(score, int)
                or not 0 <= score <= 2_147_483_647
            ):
                self._send_json(
                    400,
                    {"error": "score must be an integer between 0 and 2147483647"},
                )
                return

            score_id = store.insert(name, score)
            self._send_json(201, {"id": score_id, "name": name, "score": score})

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}")

    class LeaderboardHTTPServer(ThreadingHTTPServer):
        def server_close(self) -> None:
            super().server_close()
            store.close()

    return LeaderboardHTTPServer((host, port), LeaderboardHandler)


def main() -> None:
    load_dotenv(".env.local")
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="Run the Douda leaderboard server.")
    parser.add_argument(
        "--host",
        default=os.environ.get("DOUDA_SERVER_HOST", "127.0.0.1"),
        help="interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DOUDA_SERVER_PORT", "8765")),
        help="port to listen on (default: 8765)",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DOUDA_DB_PATH", "douda-leaderboard.sqlite3"),
        help="SQLite database path",
    )
    args = parser.parse_args()

    server = create_server(args.host, args.port, args.db)
    print(f"Douda leaderboard listening on http://{args.host}:{args.port}")
    print(f"Scores are stored in {Path(args.db).expanduser().resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Douda leaderboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
