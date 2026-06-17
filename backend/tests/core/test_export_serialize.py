import io
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pyarrow.parquet as pq

from backend.core.export.serialize import table_to_parquet


def test_parquet_roundtrip_with_types():
    rows = [
        {"id": UUID("11111111-1111-1111-1111-111111111111"), "preco": Decimal("12.34"),
         "criado": datetime(2026, 6, 1, tzinfo=timezone.utc), "meta": {"a": 1}, "n": None, "ok": True},
    ]
    cols = ["id", "preco", "criado", "meta", "n", "ok"]
    data = table_to_parquet(rows, cols)
    table = pq.read_table(io.BytesIO(data))
    assert table.column_names == cols
    rec = table.to_pylist()[0]
    assert rec["id"] == "11111111-1111-1111-1111-111111111111"
    assert rec["preco"] == "12.34"           # Decimal -> str
    assert rec["meta"] == '{"a": 1}'          # JSON string
    assert rec["ok"] is True


def test_empty_table_keeps_columns():
    data = table_to_parquet([], ["id", "nome"])
    table = pq.read_table(io.BytesIO(data))
    assert table.column_names == ["id", "nome"]
    assert table.num_rows == 0
