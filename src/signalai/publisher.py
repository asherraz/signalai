"""Deterministically rebuild the complete public state from authoritative repository state."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from signalai.clinical_network_export import export_clinical_network
from signalai.clinic_intelligence_export import export_clinic_intelligence
from signalai.clinic_simulation import export_clinic_simulation
from signalai.schemas.clinic_simulation import ClinicSimulationState
from signalai.signalrb import export_signalrb
from signalai.flagship_export import export_flagship_program
from signalai.manufacturing import initialize_manufacturing, validate_manufacturing_operational_refs
from signalai.manufacturing_export import export_flagship_manufacturing, export_manufacturing
from signalai.design_lab_export import export_design_lab, validate_design_lab_evidence
from signalai.schemas.design_lab import DesignLabWorkspace
from signalai.schemas.clinic_intelligence import ClinicIntelligenceDataset
from signalai.product_export import export_product_layer
from signalai.live_export import export_live_intelligence, merge_live_feed
from signalai.public_export import build_public_airb, export_completed_run
from signalai.schemas import (
    ClinicalNetworkState,
    DevelopmentAgenda,
    DevelopmentDocket,
    LiveRunHistory,
    PublicChange,
    PublicSignalState,
    SignalState,
    TherapeuticAssetWorkspace,
    WhatChanged,
)
from signalai.storage import publish_json
from signalai.workspace_export import export_workspace, validate_workspace_references


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
    docket_path = root / "state" / "development-docket.json"
    history_path = root / "state" / "live-runs.json"
    docket = DevelopmentDocket.model_validate_json(docket_path.read_text(encoding="utf-8")) if docket_path.exists() else None
    history = LiveRunHistory.model_validate_json(history_path.read_text(encoding="utf-8")) if history_path.exists() else None
    agenda_path = root / "state" / "development-agenda.json"
    agenda = (
        DevelopmentAgenda.model_validate_json(agenda_path.read_text(encoding="utf-8"))
        if agenda_path.exists()
        else None
    )
    if workspace.manufacturing is None:
        if agenda is None or docket is None or history is None:
            raise ValueError(
                "manufacturing compatibility initialization requires agenda, docket, and run history"
            )
        workspace = initialize_manufacturing(workspace, scientific, agenda, docket, history)
    # Some bounded/staged run fixtures intentionally omit the legacy agenda.
    # Keep those projections backward compatible; complete repository builds
    # still perform the full canonical cross-reference validation.
    if agenda is not None:
        validate_workspace_references(workspace, scientific, agenda)
    if agenda is not None and docket is not None and history is not None:
        validate_manufacturing_operational_refs(workspace.manufacturing, docket, history)
    cargo, formulation, jurisdictions = export_workspace(workspace)
    manufacturing = export_manufacturing(workspace.manufacturing)
    clinical_network = export_clinical_network(
        clinical,
        scientific,
        workspace,
        what_changed_recently=changed.summary,
    )
    clinic_data_path = root / "data" / "clinics" / "clinics.json"
    clinic_dataset = (
        ClinicIntelligenceDataset.model_validate_json(clinic_data_path.read_text(encoding="utf-8"))
        if clinic_data_path.exists() else ClinicIntelligenceDataset()
    )
    clinic_intelligence = export_clinic_intelligence(clinic_dataset)
    design_path = root / "state" / "design-lab.json"
    design_workspace = (
        DesignLabWorkspace.model_validate_json(design_path.read_text(encoding="utf-8"))
        if design_path.exists() else None
    )
    if design_workspace:
        from signalai.design_lab import migrate_design_lab
        design_workspace = migrate_design_lab(design_workspace)
        validate_design_lab_evidence(design_workspace, {item.evidence_id for item in scientific.evidence})
    design_lab = export_design_lab(design_workspace) if design_workspace else None
    simulation_path = root / "state" / "clinic-simulation.json"
    clinic_simulation = (
        export_clinic_simulation(
            ClinicSimulationState.model_validate_json(
                simulation_path.read_text(encoding="utf-8")
            )
        )
        if simulation_path.exists()
        else None
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
    live_intelligence = None
    if docket is not None and history is not None:
        live_intelligence = export_live_intelligence(docket, history)
        feed = merge_live_feed(feed, history)
    public = PublicSignalState.from_internal(
        scientific,
        generated_at=generated_at or datetime.now(timezone.utc),
        changes=changes,
        completed_stages=["selection", "analysis", "critique", "synthesis"],
        current_hypothesis=latest_run.stages.hypothesis,
        latest_run=latest_run,
        airb=airb,
        cargo=cargo,
        formulation=formulation,
        manufacturing=manufacturing,
        jurisdictions=jurisdictions,
        clinical_network=clinical_network,
        clinic_intelligence=clinic_intelligence,
        design_lab=design_lab,
        product=product,
        intelligence_feed=feed,
        live_intelligence=live_intelligence,
        clinic_simulation=clinic_simulation,
    )
    if history and history.runs:
        public = public.model_copy(update={"signal_rb": export_signalrb(root, scientific, history)})
    flagship = export_flagship_program(scientific, public.signal_rb).model_copy(
        update={"manufacturing": export_flagship_manufacturing(workspace.manufacturing)}
    )
    public = public.model_copy(update={"flagship_program": flagship})
    return public


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
