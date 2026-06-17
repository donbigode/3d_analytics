import io
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq


def _coerce(v):
    if v is None:
        return None
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str, ensure_ascii=False)
    if isinstance(v, (datetime, date, bool, int, float, str)):
        return v
    return str(v)


def table_to_parquet(rows: list[dict], columns: list[str]) -> bytes:
    """Serializa linhas (list[dict]) em Parquet, com coerção de tipos.

    Decimais/UUID viram str (sem perda); dict/list (JSONB) viram JSON string;
    datetime/bool/int/float/str ficam nativos. Colunas vazias preservam o schema.
    """
    data = {c: [_coerce(r.get(c)) for r in rows] for c in columns}
    table = pa.table(data)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()
