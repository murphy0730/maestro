from maestro.runtime.models import RunRecord
from maestro.runtime.store import ArtifactStore, RunStore


def test_snapshot_replace_is_atomic(tmp_path) -> None:
    store = RunStore(tmp_path / "runs")
    run = RunRecord(run_id="r1", objective="x")

    store.save(run)

    assert store.load("r1") == run
    assert not (tmp_path / "runs" / "r1.json.tmp").exists()


def test_artifact_returns_content_hash(tmp_path) -> None:
    ref = ArtifactStore(tmp_path / "artifacts").put(b"large result", "text/plain")

    assert ref.sha256
    assert ArtifactStore(tmp_path / "artifacts").get(ref.artifact_id) == b"large result"


def test_artifacts_with_same_content_share_the_content_address(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")

    first = store.put(b"large result", "text/plain")
    second = store.put(b"large result", "application/octet-stream")

    assert first.artifact_id == second.artifact_id == first.sha256 == second.sha256
    assert list((tmp_path / "artifacts").glob("*.bin")) == [
        tmp_path / "artifacts" / f"{first.sha256}.bin"
    ]
