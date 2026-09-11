"""Detect whether generated output changed beyond volatile export timestamps."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _without_export_time(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.pop("generatedAt", None)
    return normalized


def public_payload_has_material_change(before: str, after: str) -> bool:
    return _without_export_time(json.loads(before)) != _without_export_time(json.loads(after))


def repository_has_material_change(root: Path) -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    changed = [line[3:] for line in status if len(line) > 3]
    if not changed:
        return False
    if set(changed) != {"public/signal-state.json"}:
        return True
    before = subprocess.run(
        ["git", "show", "HEAD:public/signal-state.json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    after = (root / "public" / "signal-state.json").read_text(encoding="utf-8")
    return public_payload_has_material_change(before, after)
