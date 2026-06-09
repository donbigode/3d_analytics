"""Printables.com adapter — GraphQL search + file download.

Printables exposes a public GraphQL endpoint at https://api.printables.com/graphql/
that doesn't require auth for read queries. Two operations we use:

  1. ``search(q)``  → list of model summaries (id, name, author, license,
                       downloads, thumbnail).
  2. ``fetch_files(model_id)``  → list of downloadable files (id, name,
                                   format, public download URL).

For ``download(model_id)`` we follow the format priority 3MF → GCode → STL
declared in the design doc, fetch the chosen file's bytes, and return the
raw content + suggested filename + author + license for the caller to dedup
and persist.

Defensive across the board: GraphQL schemas drift, so every field access
is wrapped in dict.get with sensible fallbacks. Errors are surfaced verbatim
in the search payload's ``errors`` list instead of raising.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.printables.com/graphql/"
USER_AGENT = "3d-analytics/0.1 (library search; contact: operator@local)"
_TIMEOUT = httpx.Timeout(20.0)

# Printables exposes `searchPrints2` (Print = their "model") which takes a
# query string + limit. PrintType has 165 fields; we keep our request lean.
SEARCH_QUERY = """
query Search($query: String!, $limit: Int!) {
  searchPrints2(query: $query, limit: $limit) {
    totalCount
    items {
      id
      slug
      name
      summary
      downloadCount
      filesType
      license { abbreviation name }
      user { publicUsername }
      image { filePreview }
    }
  }
}
"""

# `print(id)` exposes the model's files via two pools:
#  - stls   → STLType, holds the printable model files (.stl, .3mf, .step …)
#  - gcodes → GCodeType, holds sliced gcode uploads
# The download URL itself is gated behind auth (`privateFile`), but the CDN
# directory layout leaks through ``filePreviewPath`` — preview files live in
# the same folder as the actual asset, named ``<slug>_preview.png``. Stripping
# ``_preview.png`` and appending the file's extension yields a public URL.
FILES_QUERY = """
query PrintFiles($id: ID!) {
  print(id: $id) {
    id
    name
    slug
    license { abbreviation name }
    user { publicUsername }
    stls {
      id
      name
      fileSize
      filePreviewPath
    }
    gcodes {
      id
      name
      fileSize
      filePreviewPath
    }
  }
}
"""


@dataclass(frozen=True)
class PrintablesHit:
    remote_id: str
    title: str
    summary: str | None
    author: str | None
    license_: str | None
    thumbnail_url: str | None
    source_url: str
    downloads: int | None


@dataclass(frozen=True)
class PrintablesFile:
    file_id: str
    filename: str
    download_url: str
    file_size: int | None
    fmt: str  # gcode | 3mf | stl | other


def _thumb_url(item: dict) -> str | None:
    img = item.get("image")
    if isinstance(img, dict) and img.get("filePreview"):
        return _cdn_url(img["filePreview"])
    return None


def _license_label(lic: dict | None) -> str | None:
    if not isinstance(lic, dict):
        return None
    return lic.get("abbreviation") or lic.get("name")


def _cdn_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    p = path.lstrip("/")
    # Some fields already include a leading "media/" segment, others don't.
    # Avoid producing "media/media/..." duplicates.
    if p.startswith("media/"):
        return f"https://media.printables.com/{p}"
    return f"https://media.printables.com/media/{p}"


def _file_url_from_preview(preview_path: str, original_name: str) -> str | None:
    """Derive the public CDN URL of a printable file from its sibling preview.

    Printables stores each uploaded model alongside a ``<slug>_preview.png``
    inside the same directory. The original filename in ``name`` keeps the
    real extension (``.3mf``, ``.stl`` …) while the slug used on disk is the
    lowercased, hyphenated variant — exactly what the preview path already
    encodes. So we drop ``_preview.png`` and append the original extension.

    Returns ``None`` if the preview path doesn't follow the expected pattern
    (e.g. files stored under ``previews/`` directly are renderings of
    non-printable assets like ``.step`` and can't be downloaded this way).
    """
    if not preview_path or not original_name:
        return None
    if "/stls/" not in preview_path and "/gcodes/" not in preview_path:
        return None
    suffix = "_preview.png"
    if not preview_path.endswith(suffix):
        return None
    base = preview_path[: -len(suffix)]
    ext = original_name.rsplit(".", 1)
    if len(ext) != 2:
        return None
    return _cdn_url(f"{base}.{ext[1]}")


def _model_url(model_id: str, slug: str | None) -> str:
    if slug:
        return f"https://www.printables.com/model/{model_id}-{slug}"
    return f"https://www.printables.com/model/{model_id}"


async def _graphql(client: httpx.AsyncClient, query: str, variables: dict) -> tuple[dict | None, str | None]:
    try:
        r = await client.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"User-Agent": USER_AGENT, "accept": "application/json"},
        )
        r.raise_for_status()
        body = r.json()
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:240]
    if isinstance(body, dict) and body.get("errors"):
        msg = "; ".join(
            (e.get("message") if isinstance(e, dict) else str(e)) for e in body["errors"]
        )
        return None, f"printables graphql: {msg[:240]}"
    return body.get("data") or {}, None


async def search(
    query: str, *, limit: int = 20, client: httpx.AsyncClient | None = None
) -> tuple[list[PrintablesHit], str | None]:
    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        data, err = await _graphql(client, SEARCH_QUERY, {"query": query, "limit": limit})
        if err or not data:
            return [], err
        items = ((data.get("searchPrints2") or {}).get("items") or [])
        hits: list[PrintablesHit] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            mid = str(it.get("id") or "")
            if not mid:
                continue
            user = it.get("user") or {}
            hits.append(
                PrintablesHit(
                    remote_id=mid,
                    title=it.get("name") or f"Printables #{mid}",
                    summary=it.get("summary") or None,
                    author=user.get("publicUsername") if isinstance(user, dict) else None,
                    license_=_license_label(it.get("license")),
                    thumbnail_url=_thumb_url(it),
                    source_url=_model_url(mid, it.get("slug")),
                    downloads=int(it.get("downloadCount") or 0),
                )
            )
        return hits, None
    finally:
        if own:
            await client.aclose()


async def fetch_files(
    model_id: str, *, client: httpx.AsyncClient | None = None
) -> tuple[list[PrintablesFile], dict, str | None]:
    """Return ``(files, model_info, error)``. ``model_info`` carries name +
    license + author so the caller can persist attribution even before
    download."""
    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        data, err = await _graphql(client, FILES_QUERY, {"id": model_id})
        if err or not data:
            return [], {}, err
        model = data.get("print") or {}
        files: list[PrintablesFile] = []
        for pool in ("stls", "gcodes"):
            for f in (model.get(pool) or []):
                if not isinstance(f, dict):
                    continue
                name = f.get("name") or ""
                fmt = "other"
                for candidate in ("3mf", "bgcode", "gcode", "stl"):
                    if name.lower().endswith("." + candidate):
                        fmt = candidate
                        break
                if fmt == "other":
                    continue  # skip .step, .obj and friends — not printable
                url = _file_url_from_preview(f.get("filePreviewPath") or "", name)
                if not url:
                    continue
                files.append(
                    PrintablesFile(
                        file_id=str(f.get("id") or ""),
                        filename=name,
                        download_url=url,
                        file_size=int(f.get("fileSize")) if f.get("fileSize") else None,
                        fmt=fmt,
                    )
                )
        user = model.get("user") or {}
        info = {
            "title": model.get("name"),
            "license": _license_label(model.get("license")),
            "author": user.get("publicUsername") if isinstance(user, dict) else None,
        }
        return files, info, None
    finally:
        if own:
            await client.aclose()


def pick_best_file(files: list[PrintablesFile]) -> PrintablesFile | None:
    """Prefer 3MF → GCode → STL."""
    priority = {"3mf": 0, "gcode": 1, "bgcode": 1, "stl": 2}
    candidates = [f for f in files if f.fmt in priority]
    if not candidates:
        return None
    candidates.sort(key=lambda f: priority[f.fmt])
    return candidates[0]


async def download_bytes(
    url: str, *, client: httpx.AsyncClient | None = None
) -> tuple[bytes | None, str | None]:
    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(60.0), follow_redirects=True)
    try:
        try:
            r = await client.get(url, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return r.content, None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)[:240]
    finally:
        if own:
            await client.aclose()
