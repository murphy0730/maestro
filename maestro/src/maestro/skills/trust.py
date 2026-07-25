"""Persistent script trust, bound to a skill package's content hash.

Trust is granted to *a specific set of bytes*, never to a name.  Editing any
file in the package changes its hash and silently invalidates the grant, so a
skill cannot be trusted once and then rewritten into something else.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from maestro.skills.package import compute_package_hash

_TRUST_FILE = "trust.json"


@dataclass(frozen=True)
class TrustStatus:
    level: str
    valid: bool
    package_sha256: str
    principal_id: str | None = None
    trusted_at: str | None = None

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "valid": self.valid,
            "package_sha256": self.package_sha256,
            "principal_id": self.principal_id,
            "trusted_at": self.trusted_at,
        }


class SkillTrustStore:
    """Trust records for installed skill packages, persisted next to them."""

    def __init__(self, skills_dir: Path) -> None:
        self._path = Path(skills_dir) / _TRUST_FILE

    def _read(self) -> dict[str, dict]:
        try:
            data = json.loads(self._path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        # Legacy files from the retired SkillEngine may hold other shapes;
        # anything unrecognised simply reads as "not trusted".
        return {
            name: record
            for name, record in data.items()
            if isinstance(record, dict) and isinstance(record.get("package_sha256"), str)
        }

    def _write(self, records: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), "utf-8")
        os.replace(temporary, self._path)

    def status(self, name: str, root: Path) -> TrustStatus:
        current = compute_package_hash(root)
        record = self._read().get(name)
        if record is None:
            return TrustStatus(level="untrusted", valid=True, package_sha256=current)
        matches = record.get("package_sha256") == current
        return TrustStatus(
            # A stale record is reported as untrusted *and* invalid, so the UI
            # can say "the package changed" rather than "you never trusted it".
            level="user_trusted" if matches else "untrusted",
            valid=matches,
            package_sha256=current,
            principal_id=record.get("principal_id"),
            trusted_at=record.get("trusted_at"),
        )

    def trust(self, name: str, root: Path, principal_id: str = "local-user") -> TrustStatus:
        records = self._read()
        records[name] = {
            "package_sha256": compute_package_hash(root),
            "principal_id": principal_id,
            "trusted_at": datetime.now(UTC).isoformat(),
        }
        self._write(records)
        return self.status(name, root)

    def revoke(self, name: str, root: Path) -> TrustStatus:
        records = self._read()
        if records.pop(name, None) is not None:
            self._write(records)
        return self.status(name, root)

    def is_trusted(self, name: str, root: Path) -> bool:
        status = self.status(name, root)
        return status.level == "user_trusted" and status.valid
