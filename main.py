#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import logging
import logging.handlers
import os
import posixpath
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import requests
except ModuleNotFoundError:
    requests = None


MEDIA_EXTENSIONS = {
    ".3g2", ".3gp", ".asf", ".avi", ".divx", ".flv", ".m2ts", ".m4v",
    ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".ogm", ".ogv",
    ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv",
}

ASSOCIATED_EXTENSIONS = {
    ".ass", ".idx", ".nfo", ".srt", ".ssa", ".sub",
}

IMPORT_FIX_MESSAGES = (
    "unable to parse file",
    "unknown movie",
    "not a custom format upgrade",
)

EPISODE_RE = re.compile(
    r"(?P<token>S(?P<season>\d{1,2})\s*E(?P<episode>\d{1,3})(?:\s*(?:-|E)\s*\d{1,3})*)",
    re.IGNORECASE,
)
ALT_EPISODE_RE = re.compile(
    r"(?<!\d)(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?:\s*(?:-|x)\s*\d{1,3})*",
    re.IGNORECASE,
)
SEASON_RE = re.compile(r"S\d{1,2}(?!\s*E\d)", re.IGNORECASE)
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SAMPLE_RE = re.compile(r"(^|[.\s_\-\[\(])sample([.\s_\-\]\)]|$)", re.IGNORECASE)

LOGGER = logging.getLogger("qbit_rectificarr")

DEFAULT_CONFIG = {
    "radarr": {
        "enabled": True,
        "host": "your_radarr_host",
        "port": "your_radarr_port",
        "api_key": "your_radarr_api_key",
        "ssl": False,
    },
    "sonarr": {
        "enabled": False,
        "host": "your_sonarr_host",
        "port": "your_sonarr_port",
        "api_key": "your_sonarr_api_key",
        "ssl": False,
    },
    "qbittorrent": {
        "host": "your_qbittorrent_host",
        "port": "your_qbittorrent_port",
        "username": "your_qbittorrent_username",
        "password": "your_qbittorrent_password",
        "ssl": False,
    },
}


class ConfigCreatedError(RuntimeError):
    pass


@dataclass
class AppConfig:
    name: str
    media_type: str
    host: str
    port: str
    api_key: str
    ssl: bool = False
    enabled: bool = True


class ArrClient:
    def __init__(self, config: AppConfig):
        require_requests()
        self.config = config
        scheme = "https" if config.ssl else "http"
        self.base_url = f"{scheme}://{config.host}:{config.port}"

    def api(self, method: str, endpoint: str, params: Optional[Dict] = None):
        params = dict(params or {})
        params["apikey"] = self.config.api_key
        url = f"{self.base_url}/api/v3/{endpoint.lstrip('/')}"
        response = requests.request(method, url, params=params, timeout=30)
        response.raise_for_status()
        if response.text:
            return response.json()
        return None

    def queue(self) -> List[Dict]:
        params = {
            "includeUnknownMovieItems": "true",
            "includeMovie": "true",
            "includeSeries": "true",
            "includeEpisode": "true",
            "page": 1,
            "pageSize": 250,
        }
        data = self.api("GET", "queue", params)
        return data.get("records", data if isinstance(data, list) else [])

    def history_for(self, item: Dict) -> List[Dict]:
        params = {
            "page": 1,
            "pageSize": 50,
            "sortKey": "date",
            "sortDirection": "descending",
        }
        if item.get("downloadId"):
            params["downloadId"] = item["downloadId"]

        try:
            data = self.api("GET", "history", params)
            records = data.get("records", data if isinstance(data, list) else [])
            if records:
                return records
        except Exception:
            pass

        if self.config.media_type == "radarr" and item.get("movieId"):
            return self.api("GET", "history/movie", {"movieId": item["movieId"]})

        if self.config.media_type == "sonarr" and item.get("seriesId"):
            return self.api("GET", "history/series", {"seriesId": item["seriesId"]})

        return []

    def source_title(self, item: Dict) -> Optional[str]:
        candidates = [
            item.get("sourceTitle"),
            item.get("releaseTitle"),
            item.get("downloadTitle"),
        ]

        download_id = item.get("downloadId")
        for history in self.history_for(item):
            if download_id and history.get("downloadId") != download_id:
                continue
            candidates.extend([
                history.get("sourceTitle"),
                history.get("releaseTitle"),
                history.get("downloadTitle"),
                history.get("sourceTitle", ""),
            ])

        for candidate in candidates:
            if candidate and looks_like_release_name(candidate):
                return candidate

        return next((candidate for candidate in candidates if candidate), None)


class QbitClient:
    def __init__(self, config: Dict):
        require_requests()
        scheme = "https" if config.get("ssl", False) else "http"
        self.base_url = f"{scheme}://{config['host']}:{config['port']}"
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.session = requests.Session()

    def login(self):
        response = self.session.post(
            f"{self.base_url}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
            timeout=30,
        )
        response.raise_for_status()
        if response.text != "Ok.":
            raise RuntimeError("qBittorrent authentication failed")

    def torrents(self) -> List[Dict]:
        response = self.session.get(f"{self.base_url}/api/v2/torrents/info", timeout=30)
        response.raise_for_status()
        return response.json()

    def files(self, torrent_hash: str) -> List[Dict]:
        response = self.session.get(
            f"{self.base_url}/api/v2/torrents/files",
            params={"hash": torrent_hash},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def rename_file(self, torrent_hash: str, old_path: str, new_path: str):
        response = self.session.post(
            f"{self.base_url}/api/v2/torrents/renameFile",
            data={"hash": torrent_hash, "oldPath": old_path, "newPath": new_path},
            timeout=30,
        )
        response.raise_for_status()
        if response.status_code == 409:
            raise RuntimeError(f"qBittorrent refused rename: {old_path} -> {new_path}")


def create_default_config(path: str):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=4)
        f.write("\n")


def load_config(path: str = "config.json") -> Dict:
    if not os.path.exists(path):
        create_default_config(path)
        raise ConfigCreatedError(f"Created default config at {path}. Edit it, then restart qBit-Rectificarr.")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def require_requests():
    if requests is None:
        raise RuntimeError("The Python package 'requests' is required to call Radarr, Sonarr, and qBittorrent APIs")


def setup_logging():
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_file = os.getenv("LOG_FILE", "/config/logs/qbit-rectificarr.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")

    LOGGER.setLevel(level)
    LOGGER.handlers.clear()
    LOGGER.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    LOGGER.addHandler(console_handler)

    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=int(os.getenv("LOG_MAX_BYTES", "1048576")),
                backupCount=int(os.getenv("LOG_BACKUP_COUNT", "3")),
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            LOGGER.addHandler(file_handler)
        except OSError as error:
            LOGGER.warning("Could not open log file %s: %s", log_file, error)


def is_placeholder_config(config: Dict) -> bool:
    placeholders = (
        "your_radarr_host",
        "your_radarr_port",
        "your_radarr_api_key",
        "your_sonarr_host",
        "your_sonarr_port",
        "your_sonarr_api_key",
        "your_qbittorrent_host",
        "your_qbittorrent_port",
        "your_qbittorrent_username",
        "your_qbittorrent_password",
    )
    serialized = json.dumps(config)
    return any(placeholder in serialized for placeholder in placeholders)


def make_arr_configs(config: Dict) -> List[AppConfig]:
    apps = []
    for key, media_type in (("radarr", "radarr"), ("sonarr", "sonarr")):
        app = config.get(key)
        if not app or app.get("enabled", True) is False:
            continue
        apps.append(AppConfig(
            name=key,
            media_type=media_type,
            host=app["host"],
            port=str(app["port"]),
            api_key=app["api_key"],
            ssl=app.get("ssl", False),
            enabled=app.get("enabled", True),
        ))
    return apps


def is_media_path(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in MEDIA_EXTENSIONS


def is_associated_path(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in ASSOCIATED_EXTENSIONS


def safe_filename(filename: str) -> str:
    name = INVALID_FILENAME_CHARS_RE.sub(".", filename)
    name = re.sub(r"\.{2,}", ".", name)
    return name.strip(" .")


def split_qbit_path(path: str) -> Tuple[str, str, str]:
    directory = posixpath.dirname(path)
    basename = posixpath.basename(path)
    stem, extension = posixpath.splitext(basename)
    return directory, stem, extension


def with_same_directory(old_path: str, new_basename: str) -> str:
    directory = posixpath.dirname(old_path)
    return posixpath.join(directory, new_basename) if directory else new_basename


def looks_like_release_name(value: str) -> bool:
    release_markers = ("1080", "2160", "720", "webrip", "web-dl", "bluray", "x264", "x265", "h264", "h265")
    normalized = value.lower()
    return "." in value or any(marker in normalized for marker in release_markers)


def get_status_messages(item: Dict) -> List[str]:
    messages = []
    for status in item.get("statusMessages", []) or []:
        messages.extend(status.get("messages", []) or [])
        if status.get("title"):
            messages.append(status["title"])
    return messages


def should_fix_item(item: Dict) -> bool:
    joined = " ".join(get_status_messages(item)).lower()
    has_fix_message = any(message in joined for message in IMPORT_FIX_MESSAGES)
    if not has_fix_message:
        return False

    if "wasn't grabbed by" in joined or "was not grabbed by" in joined:
        return False

    return True


def log_ignored_queue_item(item: Dict):
    state = item.get("trackedDownloadState")
    status = item.get("trackedDownloadStatus")
    messages = " | ".join(get_status_messages(item))
    has_fix_message = any(message in messages.lower() for message in IMPORT_FIX_MESSAGES)
    if not has_fix_message and state != "importPending" and status not in ("warning", "error"):
        return

    log = LOGGER.info if has_fix_message else LOGGER.debug
    log(
        "Ignoring queue item id=%s title=%s state=%s status=%s messages=%s",
        item.get("id"),
        item.get("title") or item.get("sourceTitle"),
        state,
        status,
        messages,
    )


def find_torrent(item: Dict, torrents: List[Dict]) -> Optional[Dict]:
    download_id = (item.get("downloadId") or "").lower()
    if download_id:
        for torrent in torrents:
            if torrent.get("hash", "").lower() == download_id:
                return torrent

    title_candidates = {
        (item.get("title") or "").lower(),
        (item.get("sourceTitle") or "").lower(),
    }
    for torrent in torrents:
        if torrent.get("name", "").lower() in title_candidates:
            return torrent

    return None


def build_radarr_basename(source_title: str, extension: str) -> str:
    return safe_filename(f"{source_title}{extension}")


def episode_token_from_text(text: str) -> Optional[str]:
    match = EPISODE_RE.search(text)
    if match:
        return re.sub(r"\s+", "", match.group("token")).upper()

    match = ALT_EPISODE_RE.search(text)
    if match:
        season = int(match.group("season"))
        episode = int(match.group("episode"))
        return f"S{season:02d}E{episode:02d}"

    return None


def episode_token_from_path(path: str) -> Optional[str]:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return None

    for part in [parts[-1], *reversed(parts[:-1])]:
        token = episode_token_from_text(part)
        if token:
            return token

    return None


def build_sonarr_basename(source_title: str, original_path: str, force_file_episode: bool = False) -> Optional[str]:
    _, _, extension = split_qbit_path(original_path)
    token = episode_token_from_path(original_path)
    source_episode = EPISODE_RE.search(source_title)
    if source_episode:
        if force_file_episode:
            if not token:
                return None
            title = EPISODE_RE.sub(token, source_title, count=1)
            return safe_filename(f"{title}{extension}")
        return safe_filename(f"{source_title}{extension}")

    if not token:
        return None

    if SEASON_RE.search(source_title):
        title = SEASON_RE.sub(token, source_title, count=1)
    else:
        title = f"{source_title}.{token}"

    return safe_filename(f"{title}{extension}")


def media_files_for_rename(files: List[Dict]) -> List[Dict]:
    media_files = [file for file in files if is_media_path(file.get("name", ""))]
    if len(media_files) <= 1:
        return media_files

    largest_size = max((file.get("size", 0) for file in media_files), default=0)
    filtered = []
    for file in media_files:
        path = file.get("name", "")
        size = file.get("size", 0)
        basename = posixpath.basename(path)
        looks_like_sample = bool(SAMPLE_RE.search(basename))
        is_small_sample = largest_size > 0 and size > 0 and size <= largest_size * 0.2
        is_exact_sample = posixpath.splitext(basename)[0].lower() == "sample"

        if looks_like_sample and (is_small_sample or is_exact_sample):
            LOGGER.info("Skipping sample file: %s", path)
            continue

        filtered.append(file)

    return filtered


def radarr_media_files_for_rename(files: List[Dict]) -> List[Dict]:
    media_files = media_files_for_rename(files)
    if len(media_files) <= 1:
        return media_files
    return [max(media_files, key=lambda file: file.get("size", 0))]


def associated_files_for_media(files: List[Dict], media_path: str) -> List[Dict]:
    media_directory, media_stem, _ = split_qbit_path(media_path)
    matches = []
    for file in files:
        path = file.get("name", "")
        if not is_associated_path(path):
            continue

        directory, stem, _ = split_qbit_path(path)
        if directory != media_directory:
            continue

        if stem == media_stem or stem.startswith(f"{media_stem}."):
            matches.append(file)

    return matches


def build_rename_plan(media_type: str, source_title: str, files: List[Dict]) -> List[Tuple[str, str]]:
    plan = []
    media_files = radarr_media_files_for_rename(files) if media_type == "radarr" else media_files_for_rename(files)
    force_file_episode = media_type == "sonarr" and len(media_files) > 1

    for file in media_files:
        old_path = file.get("name", "")
        if media_type == "radarr":
            _, _, extension = split_qbit_path(old_path)
            new_basename = build_radarr_basename(source_title, extension)
        else:
            new_basename = build_sonarr_basename(source_title, old_path, force_file_episode=force_file_episode)

        if not new_basename:
            continue

        new_path = with_same_directory(old_path, new_basename)
        if new_path == old_path:
            continue

        plan.append((old_path, new_path))

        _, old_stem, _ = split_qbit_path(old_path)
        new_stem, _ = posixpath.splitext(new_basename)
        for associated_file in associated_files_for_media(files, old_path):
            assoc_old = associated_file["name"]
            _, assoc_stem, assoc_ext = split_qbit_path(assoc_old)
            suffix = assoc_stem[len(old_stem):]
            assoc_new = with_same_directory(assoc_old, safe_filename(f"{new_stem}{suffix}{assoc_ext}"))
            if assoc_new != assoc_old:
                plan.append((assoc_old, assoc_new))

    return deduplicate_plan(plan)


def deduplicate_plan(plan: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen_old = set()
    seen_new = set()
    deduped = []
    for old_path, new_path in plan:
        if old_path in seen_old:
            continue
        if new_path in seen_new:
            LOGGER.warning("Skipping duplicate target: %s", new_path)
            continue
        seen_old.add(old_path)
        seen_new.add(new_path)
        deduped.append((old_path, new_path))
    return deduped


def process_app(arr: ArrClient, qbit: QbitClient, dry_run: bool = False):
    LOGGER.info("Processing %s queue", arr.config.name)
    torrents = qbit.torrents()
    checked = 0
    fixed = 0
    for item in arr.queue():
        checked += 1
        if not should_fix_item(item):
            log_ignored_queue_item(item)
            continue

        source_title = arr.source_title(item)
        if not source_title:
            LOGGER.warning("Skipping queue item %s: no source title found", item.get("id"))
            continue

        torrent = find_torrent(item, torrents)
        if not torrent:
            LOGGER.warning("Skipping %s: no matching qBittorrent torrent found", source_title)
            continue

        torrent_hash = torrent["hash"]
        files = qbit.files(torrent_hash)
        plan = build_rename_plan(arr.config.media_type, source_title, files)
        if not plan:
            LOGGER.info("Nothing to rename for %s", source_title)
            continue

        LOGGER.info("Renaming files for %s", source_title)
        for old_path, new_path in plan:
            LOGGER.info("%s%s -> %s", "[dry-run] " if dry_run else "", old_path, new_path)
            if not dry_run:
                qbit.rename_file(torrent_hash, old_path, new_path)
        fixed += 1

    LOGGER.info("Finished %s queue: checked=%s fixed=%s", arr.config.name, checked, fixed)


def run_once(config_path: str, dry_run: bool = False):
    config = load_config(config_path)
    if is_placeholder_config(config):
        raise ConfigCreatedError(f"Config at {config_path} still contains placeholder values. Edit it, then restart qBit-Rectificarr.")

    if "qbittorrent" not in config:
        raise RuntimeError("Missing qbittorrent config section")

    LOGGER.info("Starting qBit-Rectificarr cycle mode=%s config=%s", "dry-run" if dry_run else "run", config_path)
    qbit = QbitClient(config["qbittorrent"])
    qbit.login()
    LOGGER.info("Connected to qBittorrent")

    apps = make_arr_configs(config)
    if not apps:
        raise RuntimeError("No enabled Radarr/Sonarr config found")

    for app_config in apps:
        process_app(ArrClient(app_config), qbit, dry_run=dry_run)
    LOGGER.info("Cycle complete")


def main():
    setup_logging()
    mode = os.getenv("MODE", "loop").lower()
    config_path = os.getenv("CONFIG_PATH", "config.json")
    interval = int(os.getenv("RUN_INTERVAL", "300"))

    if mode not in ("run", "dry-run", "loop"):
        raise RuntimeError("MODE must be one of: run, dry-run, loop")

    LOGGER.info(
        "Booting qBit-Rectificarr mode=%s interval=%ss config=%s log_file=%s",
        mode,
        interval,
        config_path,
        os.getenv("LOG_FILE", "/config/logs/qbit-rectificarr.log"),
    )

    if mode in ("loop", "dry-run"):
        while True:
            try:
                run_once(config_path, dry_run=(mode == "dry-run"))
            except ConfigCreatedError as error:
                LOGGER.error("%s", error)
                LOGGER.error("Container is waiting. Edit the generated config file, then restart qBit-Rectificarr.")
                while True:
                    time.sleep(3600)
            except Exception:
                LOGGER.exception("Cycle failed")
            LOGGER.info("Sleeping %s seconds", interval)
            time.sleep(interval)
    else:
        try:
            run_once(config_path, dry_run=(mode == "dry-run"))
        except ConfigCreatedError as error:
            LOGGER.error("%s", error)


if __name__ == "__main__":
    main()
