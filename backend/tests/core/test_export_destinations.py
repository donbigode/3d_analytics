import backend.core.export.destinations as d
from backend.core.export.destinations import (
    DatabricksDestination, S3Destination, build_destination,
)


def test_s3_put_calls_put_object(monkeypatch):
    calls = {}

    class FakeClient:
        def put_object(self, **kw):
            calls.update(kw)

    monkeypatch.setattr(d.boto3, "client", lambda *a, **k: FakeClient())
    dest = S3Destination(bucket="b", region="us-east-1", prefix="pre",
                         access_key="ak", secret="sk")
    dest.put("20260617T000000Z/quotes.parquet", b"abc")
    assert calls["Bucket"] == "b"
    assert calls["Key"] == "pre/20260617T000000Z/quotes.parquet"
    assert calls["Body"] == b"abc"


def test_databricks_put_uses_files_api(monkeypatch):
    seen = {}

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass

    def fake_put(url, headers=None, content=None, timeout=None):
        seen["url"] = url; seen["headers"] = headers; seen["content"] = content
        return FakeResp()

    monkeypatch.setattr(d.httpx, "put", fake_put)
    dest = DatabricksDestination(host="https://x.databricks.com",
                                 token="tok", volume_path="/Volumes/c/s/v/base")
    dest.put("run/quotes.parquet", b"abc")
    assert seen["url"] == "https://x.databricks.com/api/2.0/fs/files/Volumes/c/s/v/base/run/quotes.parquet?overwrite=true"
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["content"] == b"abc"
