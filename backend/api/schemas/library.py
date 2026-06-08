from datetime import datetime
from pydantic import BaseModel


class AssetOut(BaseModel):
    id: str
    filename: str
    format: str
    size_bytes: int
    file_hash: str
    parsed_meta: dict | None
    source_url: str | None
    source_site: str | None
    source_author: str | None
    source_license: str | None
    thumbnail_url: str | None
    tags: list[str] | None
    notes: str | None
    created_at: datetime


class AssetUpdate(BaseModel):
    source_url: str | None = None
    source_author: str | None = None
    source_license: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


class RemoteSearchHit(BaseModel):
    site: str
    remote_id: str
    title: str
    author: str | None = None
    license: str | None = None
    thumbnail_url: str | None = None
    source_url: str
    downloads: int | None = None
    summary: str | None = None


class SearchResponse(BaseModel):
    query: str
    rewritten: list[str] = []   # alternate queries the LLM expanded into
    hits: list[RemoteSearchHit]
    errors: list[str] = []      # per-source failures, surfaced verbatim


class DownloadRequest(BaseModel):
    site: str
    remote_id: str
    source_url: str | None = None  # fallback when adapter needs the URL


class DownloadOut(BaseModel):
    asset: AssetOut
    duplicate: bool   # True when the hash already existed
