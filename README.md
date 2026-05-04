# qBit-Rectificarr

qBit-Rectificarr fixes Radarr/Sonarr imports where the release was grabbed with a good Custom Format score, but the downloaded file name does not contain the tags used for scoring.

It watches the Radarr and Sonarr queues for import warnings, finds the matching torrent in qBittorrent, and renames the torrent files before import so the Arr parser sees the original release tags.

## What it fixes

- Radarr files are renamed from the grabbed release name while keeping the original extension.
- Sonarr single episodes use the grabbed release name while keeping the original extension.
- Sonarr season packs inject the episode token from each file into the season release name.
- Associated subtitle/info files with the same base name are renamed with the video file.
- Sample videos are ignored when a torrent has more than one video file.
- Import warnings caused by `Unable to parse file`, `Unknown Movie`, and `Not a Custom Format upgrade` are handled.

## Examples

Radarr:

```text
sourceTitle = Nom.Release.2024.MULTI.1080p.WEBRip.x265-GROUP
file        = movie.mkv
result      = Nom.Release.2024.MULTI.1080p.WEBRip.x265-GROUP.mkv
```

Sonarr season pack:

```text
sourceTitle = Nom.Release.S01.MULTI.1080p.WEBRip.AC3.5.1.x265-P2P
file        = Nom.Release S01E01 Pilot.mkv
result      = Nom.Release.S01E01.MULTI.1080p.WEBRip.AC3.5.1.x265-P2P.mkv
```

Sonarr single episode:

```text
sourceTitle = Nom.Release.S01E22.MULTI.1080p.WEBRip.AC3.5.1.x265-P2P
file        = Episode22.mkv
result      = Nom.Release.S01E22.MULTI.1080p.WEBRip.AC3.5.1.x265-P2P.mkv
```

## Configuration

On first start, qBit-Rectificarr creates `config.json` automatically if it does not exist. Edit the generated file, then restart the container or script.

```json
{
    "radarr": {
        "enabled": true,
        "host": "your_radarr_host",
        "port": "your_radarr_port",
        "api_key": "your_radarr_api_key",
        "ssl": false
    },
    "sonarr": {
        "enabled": true,
        "host": "your_sonarr_host",
        "port": "your_sonarr_port",
        "api_key": "your_sonarr_api_key",
        "ssl": false
    },
    "qbittorrent": {
        "host": "your_qbittorrent_host",
        "port": "your_qbittorrent_port",
        "username": "your_qbittorrent_username",
        "password": "your_qbittorrent_password",
        "ssl": false
    }
}
```

## Usage

Preview planned renames once:

```console
MODE=dry-run python main.py
```

Apply renames:

```console
MODE=run python main.py
```

Run continuously every 5 minutes:

```console
MODE=loop RUN_INTERVAL=300 python main.py
```

Run it frequently enough that it can act while items are still in `importPending`. A cron job or scheduled task every few minutes is usually the right shape.

## Docker Compose

An example Compose file is available in `docker-compose.example.yml`. It is intentionally Unraid-friendly: one service, configuration through environment variables, and one appdata folder mounted to `/config`.

Run continuously:

```console
docker compose -f docker-compose.example.yml up -d --build
```

Preview planned renames with the same Compose service:

```console
docker compose -f docker-compose.example.yml run --rm -e MODE=dry-run qbit-rectificarr
```

On Unraid, set `MODE=dry-run` on the container itself. It will stay running and write logs every `RUN_INTERVAL` seconds without renaming files.

Useful environment variables:

- `MODE`: `run`, `dry-run`, or `loop`. In Docker, default is `loop`; `dry-run` stays running and repeats.
- `RUN_INTERVAL`: seconds between cycles when `MODE=loop` or `MODE=dry-run`
- `CONFIG_PATH`: path to `config.json` inside the container
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, or `ERROR`
- `LOG_FILE`: log file path inside the container, defaults to `/config/logs/qbit-rectificarr.log`
- `TZ`: container timezone

For Unraid, use a path mapping like this:

```text
Host Path:      /mnt/user/appdata/qBit-Rectificarr
Container Path: /config
Access Mode:    Read/Write
```

On first boot, the container creates:

```text
/mnt/user/appdata/qBit-Rectificarr/config.json
```

Fill it, then restart the container.

Logs are written to both the container output and:

```text
/mnt/user/appdata/qBit-Rectificarr/logs/qbit-rectificarr.log
```

## Requirements

- Python 3
- `requests`
- Radarr and/or Sonarr
- qBittorrent Web UI enabled

Install dependency:

```console
pip install requests
```
