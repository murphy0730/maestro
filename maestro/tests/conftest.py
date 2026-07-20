import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_runtime_data(tmp_path_factory):
    previous = os.environ.get("MAESTRO_DATA_DIR")
    os.environ["MAESTRO_DATA_DIR"] = str(tmp_path_factory.mktemp("maestro_runtime"))
    yield
    if previous is None:
        os.environ.pop("MAESTRO_DATA_DIR", None)
    else:
        os.environ["MAESTRO_DATA_DIR"] = previous
