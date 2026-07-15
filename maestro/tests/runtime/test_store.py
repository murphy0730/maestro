import pytest

from maestro.runtime.models import RunRecord
from maestro.runtime.store import ArtifactStore, InvalidStorageId, RunStore


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


@pytest.fixture(params=["../outside", "absolute"])
def unsafe_storage_id(tmp_path, request: pytest.FixtureRequest) -> str:
    if request.param == "absolute":
        return str(tmp_path / "outside")
    return request.param


def test_run_store_rejects_unsafe_run_ids_on_save(tmp_path, unsafe_storage_id: str) -> None:
    store = RunStore(tmp_path / "runs")

    with pytest.raises(InvalidStorageId):
        store.save(RunRecord(run_id=unsafe_storage_id, objective="x"))

    assert not (tmp_path / "outside.json").exists()


def test_run_store_rejects_unsafe_run_ids_on_load(
    tmp_path, unsafe_storage_id: str
) -> None:
    store = RunStore(tmp_path / "runs")

    with pytest.raises(InvalidStorageId):
        store.load(unsafe_storage_id)


def test_artifact_store_get_rejects_unsafe_ids(tmp_path, unsafe_storage_id: str) -> None:
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(InvalidStorageId):
        store.get(unsafe_storage_id)

    assert not (tmp_path / "outside.bin").exists()
