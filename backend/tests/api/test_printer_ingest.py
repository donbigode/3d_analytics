import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import app
from backend.infra.db import session as session_module
from backend.infra.db.models import PrinterJob
from backend.core.models import PrinterJobStatus


@pytest.mark.asyncio
async def test_printer_job_roundtrip():
    async with session_module.SessionFactory() as s:
        job = PrinterJob(
            machine="K1-oficina",
            job_uid="42",
            filename="peca.gcode",
            status="completed",
            filament_used_mm=3000,
            time_s=5000,
            raw={"foo": "bar"},
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        assert job.inbox_status == PrinterJobStatus.PENDING
        assert job.filament_used_mm == 3000


def _payload(**over):
    base = {
        "machine": "K1-oficina",
        "job_uid": "100",
        "filename": "peca.gcode",
        "status": "completed",
        "filament_used_mm": "3000",
        "print_duration_s": "5000",
        "raw": {"src": "moonraker"},
    }
    base.update(over)
    return base


async def _ingest_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def _token(monkeypatch):
    # get_settings() monta AppSettings() por chamada e o pydantic-settings lê
    # do ambiente, então a env var reflete nas instâncias criadas no request.
    monkeypatch.setenv("AGENT_INGEST_TOKEN", "sekret")
    yield "sekret"


@pytest.mark.asyncio
async def test_ingest_requires_token(_token):
    async with await _ingest_client() as c:
        r = await c.post("/ingest/print-jobs", json=_payload())
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_ingest_rejects_wrong_token(_token):
    async with await _ingest_client() as c:
        r = await c.post(
            "/ingest/print-jobs",
            json=_payload(),
            headers={"authorization": "Bearer nope"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_ingest_inserts_and_is_idempotent(_token):
    hdr = {"authorization": "Bearer sekret"}
    async with await _ingest_client() as c:
        r1 = await c.post("/ingest/print-jobs", json=_payload(job_uid="200"), headers=hdr)
        assert r1.status_code == 201, r1.text
        first_id = r1.json()["id"]
        # reenvio do mesmo (machine, job_uid) não duplica
        r2 = await c.post("/ingest/print-jobs", json=_payload(job_uid="200"), headers=hdr)
        assert r2.status_code == 200
        assert r2.json()["id"] == first_id


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_status(_token):
    hdr = {"authorization": "Bearer sekret"}
    async with await _ingest_client() as c:
        r = await c.post(
            "/ingest/print-jobs", json=_payload(status="printing"), headers=hdr
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_ingest_503_when_unconfigured(monkeypatch):
    monkeypatch.delenv("AGENT_INGEST_TOKEN", raising=False)
    async with await _ingest_client() as c:
        r = await c.post(
            "/ingest/print-jobs",
            json=_payload(),
            headers={"authorization": "Bearer whatever"},
        )
        assert r.status_code == 503
