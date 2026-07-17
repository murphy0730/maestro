"""Filesystem stores for runtime snapshots and immutable artifacts."""

import hashlib
import json
import os
import re
import asyncio
import threading
import fcntl
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from maestro.runtime.models import RunRecord


class InvalidStorageId(ValueError):
    """A storage identifier is unsafe for use as a filename component."""


_STORAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _validate_storage_id(storage_id: str) -> str:
    if not _STORAGE_ID_PATTERN.fullmatch(storage_id):
        raise InvalidStorageId(f"invalid storage identifier: {storage_id!r}")
    return storage_id


class ArtifactRef(BaseModel):
    artifact_id: str
    sha256: str
    media_type: str
    bytes: int


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def is_reproducible_artifact_ref(ref: ArtifactRef) -> bool:
    return (
        ref.artifact_id == ref.sha256
        and _SHA256_PATTERN.fullmatch(ref.artifact_id) is not None
        and ref.bytes >= 0
        and bool(ref.media_type)
    )


class RunStore:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._write_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)

    def lock_for(self, run_id: str) -> asyncio.Lock:
        """Return the process-local serialization lock for one Run."""
        return self._locks[_validate_storage_id(run_id)]

    def save(self, run: RunRecord) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        run_id = _validate_storage_id(run.run_id)
        target = self.directory / f"{run_id}.json"
        temporary = self.directory / f"{run_id}.json.tmp"
        payload = run.model_dump_json().encode("utf-8")
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        try:
            written = os.write(fd, payload)
            if written != len(payload):
                raise OSError("incomplete run snapshot write")
            os.fsync(fd)
        finally:
            os.close(fd)
        temporary.replace(target)

    def load(self, run_id: str) -> RunRecord:
        run_id = _validate_storage_id(run_id)
        return RunRecord.model_validate_json(
            (self.directory / f"{run_id}.json").read_bytes()
        )

    def compare_and_save(self, run: RunRecord, expected_revision: int) -> bool:
        """Atomically replace a snapshot only when its stored revision still matches."""
        self.directory.mkdir(parents=True, exist_ok=True)
        run_id = _validate_storage_id(run.run_id)
        lock_path = self.directory / f"{run_id}.lock"
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                try:
                    current = self.load(run.run_id)
                except FileNotFoundError:
                    if expected_revision != -1:
                        return False
                    self.save(run)
                    return True
                if current.revision != expected_revision:
                    return False
                self.save(run)
                return True
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class ArtifactStore:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def put(self, content: bytes, media_type: str) -> ArtifactRef:
        self.directory.mkdir(parents=True, exist_ok=True)
        sha256 = hashlib.sha256(content).hexdigest()
        path = self.directory / f"{sha256}.bin"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            try:
                written = os.write(fd, content)
                if written != len(content):
                    raise OSError("incomplete artifact write")
                os.fsync(fd)
            finally:
                os.close(fd)
        metadata = self.directory / f"{sha256}.json"
        if not metadata.exists():
            metadata.write_text(
                json.dumps({"media_type": media_type, "bytes": len(content)}), "utf-8"
            )
        return ArtifactRef(
            artifact_id=sha256,
            sha256=sha256,
            media_type=media_type,
            bytes=len(content),
        )

    def get(self, artifact_id: str) -> bytes:
        artifact_id = _validate_storage_id(artifact_id)
        if _SHA256_PATTERN.fullmatch(artifact_id) is None:
            raise InvalidStorageId(f"invalid artifact identifier: {artifact_id!r}")
        return (self.directory / f"{artifact_id}.bin").read_bytes()

    def media_type(self, artifact_id: str) -> str:
        artifact_id = _validate_storage_id(artifact_id)
        if _SHA256_PATTERN.fullmatch(artifact_id) is None:
            raise InvalidStorageId(f"invalid artifact identifier: {artifact_id!r}")
        data = json.loads((self.directory / f"{artifact_id}.json").read_text("utf-8"))
        return str(data["media_type"])
