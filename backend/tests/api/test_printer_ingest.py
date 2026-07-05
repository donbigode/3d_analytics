import pytest

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
