# Douda

Douda is a tiny terminal Snake game with a shared leaderboard. It has no runtime
dependencies and installs with `pip`.

## Install and play

```powershell
py -m pip install .
douda
```

Use **WASD** or the arrow keys to steer and **Q** to quit. A run is submitted
when the snake crashes or fills the board; quitting does not submit a score.
The first run asks for a player name. Set `DOUDA_PLAYER` to skip that prompt.

## Run a shared leaderboard

Start the included leaderboard service:

```powershell
douda-server
```

The server stores scores in `douda-leaderboard.sqlite3` in its working
directory and listens on `127.0.0.1:8765`. Set `DOUDA_DB_PATH` to choose another
database file. The game uses that local address by default.

For scores to be shared with other players, deploy the server on a host they can
reach and put it behind HTTPS. Bind it to the host's network interface, for
example:

```powershell
douda-server --host 0.0.0.0 --port 8765
```

On each player's computer, point the game at the public HTTPS address:

```powershell
$env:DOUDA_LEADERBOARD_URL = "https://snake.example.com"
douda
```

The service accepts score submissions without accounts, so scores are
community-submitted and are not independently verified. Use a persistent disk
for the SQLite file when hosting it. The API supports `GET /scores?limit=10&offset=0`,
`POST /scores`, and `GET /health`; pages allow browsing the leaderboard without
a fixed total-score limit.

## Development

Run the tests with:

```powershell
py -m unittest discover -s tests
```
