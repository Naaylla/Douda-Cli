# Douda

Terminal Snake with a shared leaderboard.

## Install

Once Douda is published on PyPI:

```bash
pip install douda
```

Then play:

```bash
douda
```

Use **WASD** or the arrow keys to move. Press **Q** to quit.

> **PyPI release coming soon.** The package name is not published yet.

## Leaderboard

The game submits scores to the Douda leaderboard API. To run your own API:

```bash
pip install douda
douda-server
```

Set `DOUDA_LEADERBOARD_URL` to your server URL if it is not running locally.
Configure `DATABASE_URL` on the server to use PostgreSQL; otherwise it uses
local SQLite.

## Publishing (maintainers)

Set up a PyPI Trusted Publisher for `Naaylla/Douda-Cli`, workflow
`.github/workflows/publish.yml`, environment `pypi`. Publish a GitHub Release
to upload the package. No PyPI token is needed.
