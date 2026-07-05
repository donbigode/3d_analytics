import pytest

from backend.infra.db import session as session_module
from backend.infra.db.models import PrinterJob
from backend.core.models import PrinterJobStatus


async def _mk_job(**over) -> str:
    async with session_module.SessionFactory() as s:
        job = PrinterJob(
            machine="K1", job_uid=over.pop("job_uid", "1"),
            filename="p.gcode", status="completed",
            filament_used_mm=over.pop("filament_used_mm", 3000),
            time_s=5000, raw={},
            inbox_status=over.pop("inbox_status", PrinterJobStatus.PENDING),
        )
        for k, v in over.items():
            setattr(job, k, v)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return str(job.id)


@pytest.mark.asyncio
async def test_list_shows_only_pending(auth_client):
    pend = await _mk_job(job_uid="p1")
    disc = await _mk_job(job_uid="d1", inbox_status=PrinterJobStatus.DISCARDED)
    r = await auth_client.get("/printer-jobs")
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()}
    assert pend in ids
    assert disc not in ids


@pytest.mark.asyncio
async def test_discard_marks_discarded(auth_client):
    jid = await _mk_job(job_uid="x1")
    r = await auth_client.delete(f"/printer-jobs/{jid}")
    assert r.status_code == 204
    async with session_module.SessionFactory() as s:
        rec = await s.get(PrinterJob, jid)
        assert rec.inbox_status == PrinterJobStatus.DISCARDED
