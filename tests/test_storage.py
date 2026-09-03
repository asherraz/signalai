import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from signalai.storage import RunStore, new_run_id


def test_run_ids_are_unique() -> None:
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert new_run_id(now) != new_run_id(now)


def test_run_artifacts_are_create_only(tmp_path: Path) -> None:
    store = RunStore(tmp_path, "run-test")
    store.write_json("stage.json", {"version": 1})

    with pytest.raises(FileExistsError):
        store.write_json("stage.json", {"version": 2})

    assert json.loads((store.path / "stage.json").read_text()) == {"version": 1}


def test_run_store_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe path component"):
        RunStore(tmp_path, "../outside")
