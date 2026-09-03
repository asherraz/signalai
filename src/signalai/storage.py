"""Durable JSON storage helpers for local SignalAI runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter


def new_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"run-{timestamp:%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"


class RunStore:
    """Create a unique run directory and write immutable stage artifacts."""

    def __init__(self, runs_root: Path, run_id: str) -> None:
        if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
            raise ValueError("run_id must be a single safe path component")
        self.run_id = run_id
        self.path = runs_root / run_id
        self.path.mkdir(parents=True, exist_ok=False)

    def write_json(self, filename: str, value: BaseModel | Any) -> Path:
        destination = self.path / filename
        if destination.parent != self.path or destination.name != filename:
            raise ValueError("artifact filename must not contain a directory")
        payload = (
            value.model_dump(mode="json", by_alias=True)
            if isinstance(value, BaseModel)
            else TypeAdapter(Any).dump_python(value, mode="json")
        )
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return destination


def publish_json(destination: Path, value: BaseModel) -> None:
    """Atomically replace the generated public projection."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            value.model_dump_json(indent=2, by_alias=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
