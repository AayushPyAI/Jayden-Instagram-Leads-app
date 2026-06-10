"""Workbooks in Amazon S3 — MASTER (duplicate check), NEW, DUPLICATE."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from config import (
    is_workbook_folder_id,
    workbook_folder_display_name,
    workbook_folder_duplicate_id,
    workbook_folder_ids,
    workbook_folder_master_id,
    workbook_folder_new_id,
)


def normalize_api_key(value: str | None) -> str:
    """Strip whitespace and JSON-style quotes from env / Secrets Manager values."""
    v = (value or "").strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


def _s3_bucket() -> str:
    return (os.getenv("S3_BUCKET") or "").strip()


def _s3_prefix() -> str:
    raw = (os.getenv("S3_PREFIX") or "").strip().strip("/")
    return f"{raw}/" if raw else ""


class WorkbookStorage(ABC):
    @abstractmethod
    def storage_kind(self) -> str: ...

    @abstractmethod
    def storage_display(self) -> str: ...

    @abstractmethod
    def list_workbook_index(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def list_master_workbook_names(self) -> list[str]: ...

    @abstractmethod
    def read_workbook(self, relative_posix: str) -> bytes: ...

    @abstractmethod
    def write_workbook(self, relative_posix: str, data: bytes) -> str: ...

    @abstractmethod
    def delete_workbook(self, relative_posix: str) -> None: ...

    @abstractmethod
    def workbook_exists(self, relative_posix: str) -> bool: ...

    def read_master_workbook(self, basename: str) -> bytes:
        return self.read_workbook(self.master_relative_path(basename))

    def master_relative_path(self, basename: str) -> str:
        name = Path(basename).name
        if name != basename or not name.lower().endswith(".xlsx"):
            raise ValueError("Invalid workbook name.")
        return f"{workbook_folder_master_id()}/{name}"

    def new_relative_path(self, basename: str) -> str:
        name = Path(basename).name
        if name != basename or not name.lower().endswith(".xlsx"):
            raise ValueError("Invalid workbook name.")
        return f"{workbook_folder_new_id()}/{name}"

    def duplicate_relative_path(self, basename: str) -> str:
        name = Path(basename).name
        if name != basename or not name.lower().endswith(".xlsx"):
            raise ValueError("Invalid workbook name.")
        return f"{workbook_folder_duplicate_id()}/{name}"

    def master_workbook_exists(self, basename: str) -> bool:
        return self.workbook_exists(self.master_relative_path(basename))


class S3WorkbookStorage(WorkbookStorage):
    def __init__(self, bucket: str, prefix: str) -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._client = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION"))

    def _key(self, subpath: str) -> str:
        return f"{self._prefix}{subpath.lstrip('/')}"

    def storage_kind(self) -> str:
        return "s3"

    def storage_display(self) -> str:
        return f"s3://{self._bucket}/{self._prefix}"

    def _parse_relative(self, relative_posix: str) -> tuple[str, str]:
        parts = _safe_relpath_parts(relative_posix)
        folder_id = parts[0]
        if not is_workbook_folder_id(folder_id):
            raise ValueError("Invalid workbook folder.")
        basename = parts[-1]
        if len(parts) != 2:
            raise ValueError("Workbooks must be stored directly under MASTER, NEW, or DUPLICATE.")
        if not basename.lower().endswith(".xlsx"):
            raise ValueError("Workbook must be a .xlsx file.")
        return folder_id, basename

    def _object_key(self, relative_posix: str) -> str:
        folder_id, basename = self._parse_relative(relative_posix)
        return self._key(f"{folder_id}/{basename}")

    def list_workbook_index(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for folder_id in workbook_folder_ids():
            prefix = self._key(f"{folder_id}/")
            paginator = self._client.get_paginator("list_objects_v2")
            collected: list[tuple[str, int]] = []
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents") or []:
                    key = str(obj.get("Key") or "")
                    if not key.lower().endswith(".xlsx"):
                        continue
                    base = key[len(prefix) :]
                    if "/" in base or not base:
                        continue
                    size = int(obj.get("Size") or 0)
                    collected.append((base, size))
            collected.sort(key=lambda item: item[0].casefold())
            label = workbook_folder_display_name(folder_id)
            for basename, size in collected:
                out.append(
                    {
                        "folder_id": folder_id,
                        "folder_label": label,
                        "relative_path": f"{folder_id}/{basename}",
                        "name": basename,
                        "size_bytes": size,
                    }
                )
        return out

    def list_master_workbook_names(self) -> list[str]:
        prefix = self._key(f"{workbook_folder_master_id()}/")
        names: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = str(obj.get("Key") or "")
                if not key.lower().endswith(".xlsx"):
                    continue
                base = key[len(prefix) :]
                if "/" in base or not base:
                    continue
                names.append(base)
        return sorted(names, key=str.casefold)

    def read_workbook(self, relative_posix: str) -> bytes:
        key = self._object_key(relative_posix)
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                raise FileNotFoundError("Workbook not found.") from exc
            raise

    def write_workbook(self, relative_posix: str, data: bytes) -> str:
        folder_id, basename = self._parse_relative(relative_posix)
        key = self._key(f"{folder_id}/{basename}")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return f"{folder_id}/{basename}"

    def delete_workbook(self, relative_posix: str) -> None:
        key = self._object_key(relative_posix)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def workbook_exists(self, relative_posix: str) -> bool:
        key = self._object_key(relative_posix)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False


def _safe_relpath_parts(relative_posix: str) -> tuple[str, ...]:
    rel = (relative_posix or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or "//" in rel:
        raise ValueError("Invalid workbook path.")
    parts = tuple(p for p in rel.split("/") if p and p != ".")
    if not parts or any(p == ".." for p in parts) or any(p.startswith(".") for p in parts):
        raise ValueError("Invalid workbook path.")
    return parts


_store: WorkbookStorage | None = None


def get_workbook_storage() -> WorkbookStorage:
    global _store
    if _store is not None:
        return _store
    bucket = _s3_bucket()
    if not bucket:
        raise RuntimeError("S3_BUCKET is required. Workbooks are stored only in Amazon S3.")
    _store = S3WorkbookStorage(bucket=bucket, prefix=_s3_prefix())
    return _store


def reset_workbook_storage_for_tests() -> None:
    global _store
    _store = None
