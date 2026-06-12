#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import re
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
CONFIG_PATH = ROOT / "config.json"
TPDB_BASE = "https://theposterdb.com"
TPDB_IMAGE_BASE = "https://images.theposterdb.com"
TPDB_MAX_POSTER_PAGES = 12
TPDB_MAX_SEARCH_PAGES = 6
USER_AGENT = "TPDb Plex Poster Picker/0.1 (+local app)"
PLEX_EDIT_TYPES = {"movie": "1", "show": "2", "season": "3"}
PLEX_APPLY_TIMEOUT = 8


class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Config:
    plex_url: str = ""
    plex_token: str = ""
    path_mappings: list[dict[str, str]] | None = None
    remove_overlay_label_on_apply: bool = False

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists():
            return cls(path_mappings=[])
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
        return cls(
            plex_url=str(data.get("plex_url", "")).rstrip("/"),
            plex_token=str(data.get("plex_token", "")),
            path_mappings=list(data.get("path_mappings", [])),
            remove_overlay_label_on_apply=bool(data.get("remove_overlay_label_on_apply", False)),
        )

    def save(self) -> None:
        payload = {
            "plex_url": self.plex_url.rstrip("/"),
            "plex_token": self.plex_token,
            "path_mappings": self.path_mappings or [],
            "remove_overlay_label_on_apply": self.remove_overlay_label_on_apply,
        }
        with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
            json.dump(payload, config_file, indent=2)


def request_bytes(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    method: str = "GET",
    data: bytes | None = None,
) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, headers=request_headers, method=method, data=data)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise AppError(f"Request failed with HTTP {exc.code}: {detail}", exc.code) from exc
    except TimeoutError as exc:
        raise AppError(f"Request timed out after {timeout} seconds.", 504) from exc
    except urllib.error.URLError as exc:
        raise AppError(f"Request failed: {exc.reason}", 502) from exc


def plex_url(path: str, query: dict[str, str] | None = None) -> str:
    config = Config.load()
    if not config.plex_url or not config.plex_token:
        raise AppError("Plex URL and token must be configured first.")
    params = {"X-Plex-Token": config.plex_token, **(query or {})}
    return f"{config.plex_url}{path}?{urllib.parse.urlencode(params)}"


def plex_xml(path: str, query: dict[str, str] | None = None) -> ET.Element:
    return ET.fromstring(request_bytes(plex_url(path, query)))


def map_plex_path(path: str) -> str:
    config = Config.load()
    mappings = sorted(config.path_mappings or [], key=lambda mapping: len(mapping.get("plex", "")), reverse=True)
    for mapping in mappings:
        plex_prefix = mapping.get("plex", "").rstrip("/\\") or mapping.get("plex", "")
        local_prefix = mapping.get("local", "")
        path_matches_root = path == plex_prefix or path.startswith(f"{plex_prefix}/") or path.startswith(f"{plex_prefix}\\")
        if plex_prefix and local_prefix and path_matches_root:
            return local_prefix.rstrip("/\\") + path[len(plex_prefix) :]
    return path


def media_folder(item: dict[str, Any]) -> Path:
    folder_path = item.get("folder")
    if folder_path:
        return Path(map_plex_path(folder_path))
    file_path = item.get("file")
    if not file_path:
        raise AppError("Plex did not expose a media file path for this item.")
    local_file = Path(map_plex_path(file_path))
    if item.get("type") == "show":
        return local_file
    return local_file.parent


def first_media_file(video: ET.Element) -> str:
    for part in video.findall(".//Part"):
        file_path = part.attrib.get("file")
        if file_path:
            return file_path
    return ""


def first_location_path(video: ET.Element) -> str:
    for location in video.findall("Location"):
        path = location.attrib.get("path")
        if path:
            return path
    return ""


def library_sections() -> list[dict[str, str]]:
    root = plex_xml("/library/sections")
    sections = []
    for directory in root.findall("Directory"):
        section_type = directory.attrib.get("type", "")
        if section_type in {"movie", "show"}:
            sections.append(
                {
                    "key": directory.attrib.get("key", ""),
                    "title": directory.attrib.get("title", ""),
                    "type": section_type,
                }
            )
    return sections


def library_items(section_key: str) -> list[dict[str, Any]]:
    root = plex_xml(f"/library/sections/{urllib.parse.quote(section_key)}/all")
    items = []
    for video in list(root):
        item_type = video.attrib.get("type", "")
        if item_type not in {"movie", "show"}:
            continue
        items.append(
            {
                "ratingKey": video.attrib.get("ratingKey", ""),
                "title": video.attrib.get("title", ""),
                "year": video.attrib.get("year", ""),
                "type": item_type,
                "thumb": video.attrib.get("thumb", ""),
                "guid": video.attrib.get("guid", ""),
                "file": first_location_path(video) if item_type == "show" else first_media_file(video),
                "sectionKey": section_key,
            }
        )
    return items


def season_folder_name(index: str) -> str:
    try:
        return f"Season {int(index):02d}"
    except ValueError:
        return "Season 00"


def season_items(show_key: str, section_key: str = "") -> dict[str, Any]:
    metadata = plex_xml(f"/library/metadata/{urllib.parse.quote(show_key)}")
    show = metadata.find("Directory")
    if show is None:
        raise AppError("Plex show metadata was not found.", 404)

    show_title = show.attrib.get("title", "")
    show_folder = first_location_path(show)
    show_section_key = section_key or show.attrib.get("librarySectionID", "")
    root = plex_xml(f"/library/metadata/{urllib.parse.quote(show_key)}/children")
    seasons = []
    for directory in root.findall("Directory"):
        if directory.attrib.get("type") != "season":
            continue
        season_key = directory.attrib.get("ratingKey", "") or directory.attrib.get("key", "").strip("/").split("/")[-1]
        if not season_key:
            continue
        index = directory.attrib.get("index", "")
        file_path = ""
        try:
            episodes = plex_xml(f"/library/metadata/{urllib.parse.quote(season_key)}/children")
            for episode in episodes.findall("Video"):
                file_path = first_media_file(episode)
                if file_path:
                    break
        except AppError:
            file_path = ""

        folder = ""
        if file_path:
            folder = str(Path(file_path).parent)
        elif show_folder:
            folder = str(Path(show_folder) / season_folder_name(index))

        seasons.append(
            {
                "ratingKey": season_key,
                "parentRatingKey": show_key,
                "parentTitle": show_title,
                "title": directory.attrib.get("title", season_folder_name(index)),
                "year": "",
                "index": index,
                "type": "season",
                "thumb": directory.attrib.get("thumb", ""),
                "guid": directory.attrib.get("guid", ""),
                "file": file_path,
                "folder": folder,
                "searchTitle": show_title,
                "sectionKey": show_section_key,
            }
        )
    return {"seasons": seasons, "showFolder": show_folder}


def refresh_item(rating_key: str) -> None:
    request_bytes(
        plex_url(f"/library/metadata/{urllib.parse.quote(rating_key)}/refresh", {"force": "1"}),
        method="PUT",
        timeout=PLEX_APPLY_TIMEOUT,
    )


def remove_overlay_label(item: dict[str, Any]) -> None:
    rating_key = str(item.get("ratingKey") or "")
    section_key = str(item.get("sectionKey") or "")
    item_type = str(item.get("type") or "")
    edit_type = PLEX_EDIT_TYPES.get(item_type)
    if not rating_key or not section_key or not edit_type:
        raise AppError("Plex item metadata is missing the library details needed to remove the Overlay label.")

    request_bytes(
        plex_url(
            f"/library/sections/{urllib.parse.quote(section_key)}/all",
            {
                "type": edit_type,
                "id": rating_key,
                "label.locked": "1",
                "label[].tag.tag-": "Overlay",
            },
        ),
        method="PUT",
        timeout=PLEX_APPLY_TIMEOUT,
    )


def unlock_poster_field(item: dict[str, Any]) -> None:
    rating_key = str(item.get("ratingKey") or "")
    section_key = str(item.get("sectionKey") or "")
    item_type = str(item.get("type") or "")
    edit_type = PLEX_EDIT_TYPES.get(item_type)
    if not rating_key or not section_key or not edit_type:
        raise AppError("Plex item metadata is missing the library details needed to unlock the poster field.")

    request_bytes(
        plex_url(
            f"/library/sections/{urllib.parse.quote(section_key)}/all",
            {
                "type": edit_type,
                "id": rating_key,
                "thumb.locked": "0",
            },
        ),
        method="PUT",
        timeout=PLEX_APPLY_TIMEOUT,
    )


def tpdb_get(path_or_url: str) -> str:
    url = path_or_url if path_or_url.startswith("http") else f"{TPDB_BASE}{path_or_url}"
    return request_bytes(url).decode("utf-8", errors="replace")


def absolute_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("/"):
        return f"{TPDB_BASE}{value}"
    return value


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def search_target_year(title: str) -> str:
    match = re.search(r"\((\d{4})\)", title)
    return match.group(1) if match else ""


def parse_search_targets(html: str, media_type: str) -> list[dict[str, str]]:
    candidates = []
    category = "posters" if media_type in {"movie", "show", "season"} else "posters"
    pattern = re.compile(r'<a[^>]+href="((?:https://theposterdb\.com)?/posters/\d+)"[^>]*>(.*?)</a>', re.I | re.S)
    for match in pattern.finditer(html):
        title = clean_text(match.group(2))
        if not title:
            continue
        candidates.append(
            {
                "title": title,
                "url": absolute_url(unescape(match.group(1))),
                "category": category,
                "year": search_target_year(title),
            }
        )
    return candidates


def tpdb_search_targets(term: str, media_type: str, max_pages: int = TPDB_MAX_SEARCH_PAGES) -> dict[str, Any]:
    section = "shows" if media_type in {"show", "season"} else "movies"
    query = urllib.parse.urlencode({"term": term, "section": section})
    page_url = f"/search?{query}"
    pages_fetched = 0
    has_more = False
    seen: set[str] = set()
    targets: list[dict[str, str]] = []

    while page_url and pages_fetched < max_pages:
        html = tpdb_get(page_url)
        pages_fetched += 1
        for candidate in parse_search_targets(html, media_type):
            key = candidate["url"]
            if key in seen:
                continue
            seen.add(key)
            targets.append(candidate)
        page_url = next_tpdb_page(html)
        has_more = bool(page_url)

    return {
        "targets": targets,
        "pagesFetched": pages_fetched,
        "hasMore": has_more,
        "maxPages": max_pages,
    }


def poster_asset_url(asset_id: str) -> str:
    return f"{TPDB_BASE}/api/assets/{asset_id}/view"


def parse_posters(html: str) -> list[dict[str, str]]:
    posters: list[dict[str, str]] = []
    card_pattern = re.compile(r'<div class="hovereffect rounded-poster">(.*?)</div>\s*</div>\s*</div>', re.I | re.S)
    for card in card_pattern.findall(html):
        image_match = re.search(r'type="image/jpeg"[^>]+srcset="([^"]+)"', card, re.I)
        if not image_match:
            image_match = re.search(r'type="image/webp"[^>]+srcset="([^"]+)"', card, re.I)
        poster_id_match = re.search(r"data-poster-id='(\d+)'", card)
        title_match = re.search(r'<p class="p-0 mb-1 text-break">(.*?)</p>', card, re.I | re.S)
        creator_match = re.search(r'<p class="uploaded-by[^"]*"[^>]*>\s*by\s*<a[^>]+>(.*?)</a>', card, re.I | re.S)
        if not image_match:
            continue
        preview_url = absolute_url(image_match.group(1))
        poster_id = poster_id_match.group(1) if poster_id_match else preview_url
        posters.append(
            {
                "id": poster_id,
                "title": clean_text(title_match.group(1)) if title_match else f"TPDb poster {poster_id}",
                "imageUrl": poster_asset_url(poster_id) if poster_id.isdigit() else preview_url,
                "previewUrl": preview_url,
                "pageUrl": f"{TPDB_BASE}/poster/{poster_id}" if poster_id.isdigit() else "",
                "creator": clean_text(creator_match.group(1)) if creator_match else "",
            }
        )

    if posters:
        return posters

    asset_ids = set(re.findall(r"/api/assets/(\d+)(?:/view)?", html))
    asset_ids.update(re.findall(r"/poster/(\d+)", html))

    for asset_id in sorted(asset_ids, key=lambda item: int(item)):
        posters.append(
            {
                "id": asset_id,
                "title": f"TPDb asset {asset_id}",
                "imageUrl": poster_asset_url(asset_id),
                "pageUrl": f"{TPDB_BASE}/poster/{asset_id}",
                "creator": "",
            }
        )

    link_blocks = re.findall(r'(<a[^>]+href="/poster/\d+"[^>]*>.*?</a>)', html, re.I | re.S)
    for block in link_blocks:
        poster_id_match = re.search(r'/poster/(\d+)', block)
        if not poster_id_match:
            continue
        poster_id = poster_id_match.group(1)
        creator_match = re.search(r'/(?:user|profile)/([^"/?#]+)', block)
        title_match = re.search(r'(?:alt|title)="([^"]+)"', block)
        for poster in posters:
            if poster["id"] == poster_id:
                poster["creator"] = urllib.parse.unquote(creator_match.group(1)) if creator_match else poster["creator"]
                poster["title"] = clean_text(title_match.group(1)) if title_match else poster["title"]
                break

    return posters


def next_tpdb_page(html: str) -> str:
    match = re.search(r'<a[^>]+href="([^"]+)"[^>]+rel="next"', html, re.I)
    if not match:
        match = re.search(r'<a[^>]+rel="next"[^>]+href="([^"]+)"', html, re.I)
    return absolute_url(unescape(match.group(1))) if match else ""


def tpdb_posters(target_url: str, max_pages: int | None = TPDB_MAX_POSTER_PAGES) -> dict[str, Any]:
    posters: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_pages: set[str] = set()
    page_url = target_url
    pages_fetched = 0
    has_more = False

    while page_url and page_url not in seen_pages and (max_pages is None or pages_fetched < max_pages):
        seen_pages.add(page_url)
        html = tpdb_get(page_url)
        pages_fetched += 1
        for poster in parse_posters(html):
            poster_id = poster.get("id") or poster.get("imageUrl", "")
            if poster_id in seen_ids:
                continue
            seen_ids.add(poster_id)
            posters.append(poster)
        page_url = next_tpdb_page(html)
        has_more = bool(page_url)

    return {
        "posters": posters,
        "pagesFetched": pages_fetched,
        "hasMore": has_more,
        "maxPages": max_pages,
    }


def fetch_image(image_url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(image_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read(), response.headers.get("Content-Type", "image/jpeg")


def choose_extension(content_type: str, image_url: str) -> str:
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    path_extension = Path(urllib.parse.urlparse(image_url).path).suffix
    if path_extension.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if path_extension.lower() == ".jpeg" else path_extension.lower()
    return ".jpg"


def local_poster_filename(item: dict[str, Any], extension: str) -> str:
    return f"{local_poster_stem(item)}{extension}"


def local_poster_stem(item: dict[str, Any]) -> str:
    if item.get("type") != "season":
        return "poster"

    index = str(item.get("index") or "")
    if index == "0" or str(item.get("title") or "").strip().lower() == "specials":
        return "season-specials-poster"
    try:
        return f"season{int(index):02d}"
    except ValueError:
        return "poster"


def remove_stale_local_posters(folder: Path, destination: Path, stem: str) -> None:
    for extension in (".jpg", ".jpeg", ".png", ".webp"):
        stale_path = folder / f"{stem}{extension}"
        if stale_path != destination and stale_path.exists():
            stale_path.unlink()


def save_local_poster(image_url: str, item: dict[str, Any], content: bytes, content_type: str) -> dict[str, str]:
    extension = choose_extension(content_type, image_url)
    folder = media_folder(item)
    folder.mkdir(parents=True, exist_ok=True)
    stem = local_poster_stem(item)
    destination = folder / f"{stem}{extension}"
    remove_stale_local_posters(folder, destination, stem)
    destination.write_bytes(content)
    return {"mode": "local", "path": str(destination), "bytes": str(len(content))}


def upload_plex_poster(item: dict[str, Any], content: bytes, content_type: str) -> dict[str, str]:
    rating_key = str(item.get("ratingKey") or "")
    if not rating_key:
        raise AppError("Plex did not expose a rating key for this item.")
    request_bytes(
        plex_url(f"/library/metadata/{urllib.parse.quote(rating_key)}/posters"),
        headers={"Content-Type": content_type or "image/jpeg"},
        method="POST",
        data=content,
        timeout=45,
    )
    return {"mode": "plex", "ratingKey": rating_key, "bytes": str(len(content))}


def apply_poster(image_url: str, item: dict[str, Any], mode: str) -> dict[str, str | bool]:
    config = Config.load()
    content, content_type = fetch_image(image_url)
    overlay_label_removed = False
    if mode == "plex":
        result: dict[str, str | bool] = upload_plex_poster(item, content, content_type)
        if config.remove_overlay_label_on_apply:
            remove_overlay_label(item)
            overlay_label_removed = True
    elif mode == "local":
        result = save_local_poster(image_url, item, content, content_type)
        try:
            if config.remove_overlay_label_on_apply:
                remove_overlay_label(item)
                overlay_label_removed = True
            rating_key = str(item.get("ratingKey") or "")
            if rating_key:
                unlock_poster_field(item)
                refresh_item(rating_key)
        except AppError as exc:
            result["plexUpdateError"] = str(exc)
    else:
        raise AppError("Unknown poster apply mode.")

    result["overlayLabelRemoved"] = overlay_label_removed
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "TPDbPlexPosterPicker/0.1"

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.handle_api_get(parsed)
                return
            self.serve_static(parsed.path)
        except AppError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/config":
                payload = self.read_json()
                Config(
                    plex_url=str(payload.get("plex_url", "")).rstrip("/"),
                    plex_token=str(payload.get("plex_token", "")),
                    path_mappings=list(payload.get("path_mappings", [])),
                    remove_overlay_label_on_apply=bool(payload.get("remove_overlay_label_on_apply", False)),
                ).save()
                self.send_json({"ok": True})
                return
            if parsed.path == "/api/apply":
                payload = self.read_json()
                item = payload.get("item") or {}
                image_url = str(payload.get("imageUrl") or "")
                mode = str(payload.get("mode") or "local")
                if not image_url:
                    raise AppError("No poster image URL provided.")
                result = apply_poster(image_url, item, mode)
                self.send_json({"ok": True, **result})
                return
            if parsed.path == "/api/shutdown":
                if self.headers.get("X-TPDB-Stop") != "1":
                    raise AppError("Shutdown request is missing the stop header.", 403)
                self.send_json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            raise AppError("Unknown endpoint.", 404)
        except AppError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def handle_api_get(self, parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/config":
            self.send_json(Config.load().__dict__)
        elif parsed.path == "/api/libraries":
            self.send_json({"libraries": library_sections()})
        elif parsed.path == "/api/items":
            section_key = params.get("section", [""])[0]
            if not section_key:
                raise AppError("Missing section.")
            self.send_json({"items": library_items(section_key)})
        elif parsed.path == "/api/seasons":
            show_key = params.get("show", [""])[0]
            if not show_key:
                raise AppError("Missing show.")
            section_key = params.get("section", [""])[0]
            self.send_json(season_items(show_key, section_key))
        elif parsed.path == "/api/tpdb/search":
            term = params.get("term", [""])[0]
            media_type = params.get("type", ["movie"])[0]
            if not term:
                raise AppError("Missing search term.")
            max_pages = int(params.get("maxPages", [str(TPDB_MAX_SEARCH_PAGES)])[0])
            max_pages = max(1, min(max_pages, TPDB_MAX_SEARCH_PAGES))
            self.send_json(tpdb_search_targets(term, media_type, max_pages))
        elif parsed.path == "/api/tpdb/posters":
            url = params.get("url", [""])[0]
            if not url:
                raise AppError("Missing TPDb target URL.")
            max_pages = None
            if params.get("allPages", [""])[0] != "1":
                max_pages = int(params.get("maxPages", [str(TPDB_MAX_POSTER_PAGES)])[0])
                max_pages = max(1, min(max_pages, TPDB_MAX_POSTER_PAGES))
            self.send_json(tpdb_posters(url, max_pages))
        elif parsed.path == "/api/proxy-image":
            url = params.get("url", [""])[0]
            if not (url.startswith(TPDB_BASE) or url.startswith(TPDB_IMAGE_BASE)):
                raise AppError("Only TPDb images can be proxied.")
            content = request_bytes(url)
            content_type = mimetypes.guess_type(urllib.parse.urlparse(url).path)[0] or "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            raise AppError("Unknown endpoint.", 404)

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        requested = (STATIC_ROOT / path.lstrip("/")).resolve()
        if not str(requested).startswith(str(STATIC_ROOT.resolve())) or not requested.exists():
            raise AppError("Not found.", 404)
        content = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(requested))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body or "{}")

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))


def main() -> None:
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"TPDb Plex Poster Picker running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
