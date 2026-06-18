import io

import pytest
import sqlalchemy as sa
from PIL import Image

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, QuoteItem, User


def _png(w: int = 1200, h: int = 900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


async def _quote_with_item():
    async with session_module.SessionFactory() as s:
        user = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                  status=QuoteStatus.DRAFT.value)
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={}, quantity=1)
        s.add(item); await s.commit()
        return str(q.id), str(item.id)


@pytest.mark.asyncio
async def test_upload_cover_and_item_photo(auth_client):
    qid, item_id = await _quote_with_item()

    # capa (2000x1500 -> redimensiona pra 1600 no maior lado)
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("capa.png", _png(2000, 1500), "image/png")})
    assert r.status_code == 200, r.text
    cover = r.json()
    assert cover["quote_item_id"] is None
    assert cover["url"].endswith("/raw")
    assert max(cover["width"], cover["height"]) == 1600

    # foto de item
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("p.png", _png(800, 600), "image/png")},
                               data={"quote_item_id": item_id})
    assert r.status_code == 200, r.text
    assert r.json()["quote_item_id"] == item_id

    # aparece no QuoteOut (capa) e no item
    qq = (await auth_client.get(f"/quotes/{qid}")).json()
    assert len(qq["photos"]) == 1
    assert len(qq["items"][0]["photos"]) == 1

    # /raw serve a imagem
    raw = await auth_client.get(cover["url"])
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/jpeg"

    # PDF gera com foto presente
    pdf = await auth_client.get(f"/quotes/{qid}/pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    # delete remove e /raw vira 404
    d = await auth_client.delete(f"/quotes/{qid}/photos/{cover['id']}")
    assert d.status_code == 204
    assert (await auth_client.get(cover["url"])).status_code == 404


@pytest.mark.asyncio
async def test_item_from_another_quote_rejected(auth_client):
    qid, _ = await _quote_with_item()
    _other_qid, other_item_id = await _quote_with_item()
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("p.png", _png(), "image/png")},
                               data={"quote_item_id": other_item_id})
    assert r.status_code == 400, r.text
