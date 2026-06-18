import io
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.infra.storage import quote_photos


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_save_photo_resizes_and_reencodes_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(quote_photos, "get_settings",
                        lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    saved = quote_photos.save_photo(_png(4000, 3000), "foto.PNG")
    assert saved.content_type == "image/jpeg"
    assert max(saved.width, saved.height) == 1600          # reduziu pro lado maior
    assert saved.storage_path.startswith("quote_photos/")
    assert (tmp_path / saved.storage_path).exists()
    assert saved.size_bytes > 0


def test_save_photo_rejects_bad_type(tmp_path, monkeypatch):
    monkeypatch.setattr(quote_photos, "get_settings",
                        lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    with pytest.raises(ValueError):
        quote_photos.save_photo(b"not an image", "evil.txt")
