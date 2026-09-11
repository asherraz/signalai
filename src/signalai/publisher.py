"""Deterministically rebuild the complete public state from authoritative repository state."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from signalai.clinical_network_export import export_clinical_network
from signalai.product_export import export_product_layer
from signalai.live_export import export_live_intelligence, merge_live_feed
from signalai.public_export import build_public_airb, export_completed_run
from signalai.schemas import (
    ClinicalNetworkState,
    DevelopmentDocket,
    LiveRunHistory,
    PublicChange,
    PublicSignalState,
    SignalState,
    TherapeuticAssetWorkspace,
    WhatChanged,
)
from signalai.storage import publish_json
from signalai.workspace_export import export_workspace


def build_current_public_state(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> PublicSignalState:
    """Build a full projection without consulting an older public artifact."""

    scientific = SignalState.model_validate_json(
        (root / "state" / "signal-state.json").read_text(encoding="utf-8")
    )
    workspace = TherapeuticAssetWorkspace.model_validate_json(
        (root / "state" / "asset-development.json").read_text(encoding="utf-8")
    )
    clinical = ClinicalNetworkState.model_validate_json(
        (root / "state" / "clinical-network.json").read_text(encoding="utf-8")
    )
    run_dir = root / "runs" / scientific.run_id
    if not (run_dir / "09-what-changed.json").exists():
        compatible = sorted(
            path
            for path in (root / "runs").iterdir()
            if path.is_dir()
            and (path / "09-what-changed.json").exists()
            and (path / "03-selected-task.json").exists()
        )
        if not compatible:
            raise FileNotFoundError("no completed daily run is available for legacy latestRun")
        run_dir = compatible[-1]
    latest_run = export_completed_run(run_dir)
    changed = WhatChanged.model_validate_json(
        (run_dir / "09-what-changed.json").read_text(encoding="utf-8")
    )
    changes = [
        PublicChange(
            changeId=f"{changed.run_id}-daily-change",
            summary=changed.summary,
        )
    ]
    cargo, formulation, jurisdictions = export_workspace(workspace)
    clinical_network = export_clinical_network(
        clinical,
        scientific,
        workspace,
        what_changed_recently=changed.summary,
    )
    airb = build_public_airb(latest_run, scientific.program.program_id)
    product, feed = export_product_layer(
        scientific,
        workspace,
        clinical,
        clinical_network,
        changes=changes,
        latest_run=latest_run,
    )
    docket_path = root / "state" / "development-docket.json"
    history_path = root / "state" / "live-runs.json"
    live_intelligence = None
    if docket_path.exists() and history_path.exists():
        docket = DevelopmentDocket.model_validate_json(docket_path.read_text(encoding="utf-8"))
        history = LiveRunHistory.model_validate_json(history_path.read_text(encoding="utf-8"))
        live_intelligence = export_live_intelligence(docket, history)
        feed = merge_live_feed(feed, history)
    return PublicSignalState.from_internal(
        scientific,
        generated_at=generated_at or datetime.now(timezone.utc),
        changes=changes,
        completed_stages=["selection", "analysis", "critique", "synthesis"],
        current_hypothesis=latest_run.stages.hypothesis,
        latest_run=latest_run,
        airb=airb,
        cargo=cargo,
        formulation=formulation,
        jurisdictions=jurisdictions,
        clinical_network=clinical_network,
        product=product,
        intelligence_feed=feed,
        live_intelligence=live_intelligence,
    )


def publish_current_public_state(
    root: Path,
    *,
    destination: Path | None = None,
    generated_at: datetime | None = None,
) -> PublicSignalState:
    """Build, validate, and atomically publish the complete frontend state."""

    state = build_current_public_state(root, generated_at=generated_at)
    publish_json(destination or root / "public" / "signal-state.json", state)
    return state
