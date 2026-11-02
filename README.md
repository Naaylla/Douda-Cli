# Douda

Douda is a terminal Snake game with a leaderboard. The game runs locally; to
share scores across players, run the leaderboard API on a host they can reach.
The API stores scores in PostgreSQL when `DATABASE_URL` is configured, or in a
local SQLite file otherwise.

## Install

Install directly from this repository:

```powershell
py -m pip install git+https://github.com/Naaylla/Douda-Cli.git
```

Or clone the repository and install the local package:

```powershell
git clone https://github.com/Naaylla/Douda-Cli.git
cd Douda-Cli
py -m pip install .
```

Then start a game:

```powershell
douda
```

Use **WASD** or the arrow keys to steer and **Q** to quit. A run is submitted
when the snake crashes or fills the board; quitting does not submit a score.
Enter a player name when prompted, or set `DOUDA_PLAYER` to skip the prompt.

## Run a leaderboard server

Start the API locally:

```powershell
douda-server
```

By default, it listens on `127.0.0.1:8765` and saves scores to
`douda-leaderboard.sqlite3` in its working directory. Set `DOUDA_DB_PATH` to
choose another SQLite file. The server loads local environment variables from
`.env.local` or `.env`.

To share scores with other players, deploy the API to a public host with a
persistent database. Set `DATABASE_URL` in the server's environment to a pooled
PostgreSQL connection string. For example, on a web-service host that provides
a `PORT` variable:

- **Build command:** `python -m pip install .`
- **Start command:** `python -m douda.server --host 0.0.0.0 --port $PORT`
- **Environment:** `DATABASE_URL` set to the database connection string

Keep database credentials private; do not commit them to the repository. When
using PostgreSQL, Douda creates its `douda_scores` table and leaderboard index
on server startup. PostgreSQL keeps scores across service restarts and deploys.
Without `DATABASE_URL`, the server falls back to local SQLite, which may not
persist on hosted services.

Point each player's Douda installation to the public API URL:

```powershell
$env:DOUDA_LEADERBOARD_URL = "https://your-leaderboard-host.example"
douda
```

The server exposes:

- `GET /health` — health check
- `GET /scores?limit=10&offset=0` — paginated leaderboard
- `POST /scores` — submit a score

The root path `/` is not a website. Scores are community-submitted without
accounts and are not independently verified. Do not treat this unauthenticated
API as cheat-resistant.

## Development

```powershell
py -m pip install -e .
py -m unittest discover -s tests
npm run build
```
