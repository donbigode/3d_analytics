from typing import Protocol

import boto3
import httpx


class Destination(Protocol):
    def put(self, rel_path: str, data: bytes) -> None: ...


class S3Destination:
    def __init__(self, bucket: str, region: str | None, prefix: str | None,
                 access_key: str | None, secret: str | None) -> None:
        self.bucket = bucket
        self.region = region
        self.prefix = (prefix or "").rstrip("/")
        self.access_key = access_key
        self.secret = secret

    def put(self, rel_path: str, data: bytes) -> None:
        client = boto3.client(
            "s3", region_name=self.region,
            aws_access_key_id=self.access_key, aws_secret_access_key=self.secret,
        )
        key = f"{self.prefix}/{rel_path}" if self.prefix else rel_path
        client.put_object(Bucket=self.bucket, Key=key, Body=data)


class DatabricksDestination:
    def __init__(self, host: str, token: str, volume_path: str) -> None:
        self.host = host.rstrip("/")
        self.token = token
        self.volume_path = volume_path.rstrip("/")

    def put(self, rel_path: str, data: bytes) -> None:
        url = f"{self.host}/api/2.0/fs/files{self.volume_path}/{rel_path}?overwrite=true"
        resp = httpx.put(url, headers={"Authorization": f"Bearer {self.token}"},
                         content=data, timeout=60)
        resp.raise_for_status()


def build_destination(cfg) -> Destination:
    if cfg.destination == "databricks":
        if not (cfg.databricks_host and cfg.databricks_token and cfg.databricks_volume_path):
            raise ValueError("databricks destination não configurado (host/token/volume)")
        return DatabricksDestination(cfg.databricks_host, cfg.databricks_token, cfg.databricks_volume_path)
    if cfg.destination == "s3":
        if not cfg.s3_bucket:
            raise ValueError("s3 destination não configurado (bucket)")
        return S3Destination(cfg.s3_bucket, cfg.s3_region, cfg.s3_prefix,
                             cfg.s3_access_key_id, cfg.s3_secret_access_key)
    raise ValueError(f"destino desconhecido: {cfg.destination}")
