from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from website_capture.contracts import ArtifactStore, StoredArtifact


class LocalArtifactStore:
    """Filesystem adapter; replaceable with R2/S3 without changing capture logic."""

    key = "local_filesystem"

    def __init__(self, root: str | Path = "artifacts/website-captures") -> None:
        self.root = Path(root).expanduser().resolve()

    def put(
        self,
        *,
        business_id: str,
        name: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact:
        safe_business_id = _safe_segment(business_id)
        safe_name = _safe_segment(name)
        target = self.root / safe_business_id / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredArtifact(
            uri=target.as_uri(),
            content_type=content_type,
            size_bytes=len(content),
        )

    def put_json(
        self,
        *,
        business_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> StoredArtifact:
        return self.put(
            business_id=business_id,
            name=name,
            content=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )


class S3ArtifactStore:
    """Private S3-compatible storage for persistent capture artifacts."""

    key = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "website-captures",
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket.strip()
        if not self.bucket:
            raise ValueError("artifact bucket is required")
        self.prefix = prefix.strip().strip("/")
        self.client = client or _create_s3_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    def put(
        self,
        *,
        business_id: str,
        name: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact:
        key_parts = [
            part
            for part in (
                self.prefix,
                _safe_segment(business_id),
                _safe_segment(name),
            )
            if part
        ]
        object_key = "/".join(key_parts)
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
        )
        return StoredArtifact(
            uri=f"s3://{self.bucket}/{object_key}",
            content_type=content_type,
            size_bytes=len(content),
        )

    def put_json(
        self,
        *,
        business_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> StoredArtifact:
        return self.put(
            business_id=business_id,
            name=name,
            content=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip(".-")
    if not cleaned:
        raise ValueError("artifact path segment is empty")
    return cleaned[:180]


def artifact_store_from_settings(settings: Any) -> ArtifactStore:
    backend = str(settings.website_capture_storage_backend).strip().lower()
    if backend == "local":
        return LocalArtifactStore(settings.website_capture_artifact_root)
    if backend == "s3":
        return S3ArtifactStore(
            bucket=str(settings.website_capture_s3_bucket or ""),
            prefix=settings.website_capture_s3_prefix,
            endpoint_url=settings.website_capture_s3_endpoint_url,
            region=settings.website_capture_s3_region,
            access_key_id=settings.website_capture_s3_access_key_id,
            secret_access_key=settings.website_capture_s3_secret_access_key,
        )
    raise ValueError(f"unsupported website capture storage backend: {backend}")


def _create_s3_client(
    *,
    endpoint_url: str | None,
    region: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
) -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - depends on worker image extras
        raise RuntimeError(
            "S3 artifact storage requires the website-capture optional dependencies"
        ) from exc

    options: dict[str, str] = {}
    if endpoint_url:
        options["endpoint_url"] = endpoint_url
    if region:
        options["region_name"] = region
    if access_key_id:
        options["aws_access_key_id"] = access_key_id
    if secret_access_key:
        options["aws_secret_access_key"] = secret_access_key
    return boto3.client("s3", **options)
