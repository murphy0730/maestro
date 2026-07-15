"""Filesystem stores for runtime snapshots and immutable artifacts."""

import hashlib
import os
import re
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


class RunStore:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

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
        return ArtifactRef(
            artifact_id=sha256,
            sha256=sha256,
            media_type=media_type,
            bytes=len(content),
        )

    def get(self, artifact_id: str) -> bytes:
        artifact_id = _validate_storage_id(artifact_id)
        return (self.directory / f"{artifact_id}.bin").read_bytes()
