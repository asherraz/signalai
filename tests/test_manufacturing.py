import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.manufacturing import (
    apply_validated_manufacturing_update, build_initial_manufacturing,
    initialize_manufacturing, validate_manufacturing_operational_refs,
)
from signalai.manufacturing_export import export_manufacturing
from signalai.publisher import build_current_public_state
from signalai.schemas import (
    CoaRecord, DevelopmentAgenda, DevelopmentDocket, LiveRunHistory,
    ManufacturingLot, SignalState, StabilityProgram, StabilityTimepoint,
    TestResult as ManufacturingTestResult, TherapeuticAssetWorkspace,
)

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    return (
        TherapeuticAssetWorkspace.model_validate_json((ROOT / "state/asset-development.json").read_text()),
        SignalState.model_validate_json((ROOT / "state/signal-state.json").read_text()),
        DevelopmentAgenda.model_validate_json((ROOT / "state/development-agenda.json").read_text()),
        DevelopmentDocket.model_validate_json((ROOT / "state/development-docket.json").read_text()),
        LiveRunHistory.model_validate_json((ROOT / "state/live-runs.json").read_text()),
    )


def test_canonical_manufacturing_maps_supported_state_without_fictional_records():
    workspace, state, _, _, _ = inputs()
    mfg = workspace.manufacturing
    assert mfg is not None and mfg.program_id == "SGL-001"
    assert mfg.product_definition.route == state.program.route_of_administration
    assert mfg.product_definition.drug_substance_identity is None
    assert mfg.product_definition.purification_fractionation_state is None
    assert "Secretome retaining EVs versus a small-EV preparation." in mfg.product_definition.unresolved_decisions
    assert mfg.potency_strategy.state == "evidence_gap"
    assert not mfg.potency_strategy.particle_count_is_established_potency
    assert not mfg.potency_strategy.validated_acceptance_criteria
    assert mfg.potency_strategy.latest_determination_id == "signalrb-run-20260915T182041Z-37610c33c578"
    assert mfg.potency_strategy.prior_state_preserved is True
    assert [item.process_stage_id for item in mfg.process_stages] == [
        "process-source-qualification", "process-cell-bank-strategy", "process-msc-expansion",
        "process-conditioning", "process-harvest", "process-clarification",
        "process-concentration-fraction-handling", "process-formulation",
        "process-fill-finish", "process-storage",
    ]
    assert len(mfg.readiness) == 12
    assert mfg.lots == mfg.test_results == mfg.stability_programs == mfg.coa_records == []
    assert len(mfg.specifications) == 1
    assert mfg.specifications[0].approval_state == "proposed"
    assert mfg.specifications[0].acceptance_criteria == []
    assert all(item.validation_status != "verified" for item in mfg.test_methods)


def test_backward_compatible_initialization_is_deterministic_and_idempotent():
    workspace, state, agenda, docket, history = inputs()
    payload = workspace.model_dump(mode="python")
    payload.pop("manufacturing")
    payload["schema_version"] = "1.0"
    legacy = TherapeuticAssetWorkspace.model_validate(payload)
    assert legacy.manufacturing is None
    migrated = initialize_manufacturing(legacy, state, agenda, docket, history)
    assert migrated.manufacturing == build_initial_manufacturing(legacy, state, agenda, docket, history)
    assert initialize_manufacturing(migrated, state, agenda, docket, history) is migrated
    assert migrated.cargo == legacy.cargo
    assert migrated.formulation == legacy.formulation
    assert migrated.jurisdictions == legacy.jurisdictions


def test_particle_count_cannot_be_promoted_to_established_potency():
    mfg = inputs()[0].manufacturing
    payload = mfg.potency_strategy.model_dump(mode="python")
    payload["particle_count_is_established_potency"] = True
    with pytest.raises(ValidationError, match="particle count"):
        type(mfg.potency_strategy).model_validate(payload)


def test_manufacturing_entity_ids_are_unique_and_stable():
    mfg = inputs()[0].manufacturing
    payload = mfg.model_dump(mode="python")
    payload["test_methods"].append(payload["test_methods"][0])
    with pytest.raises(ValidationError, match="duplicate method ID"):
        type(mfg).model_validate(payload)


def test_verified_quality_and_potency_require_real_criteria():
    mfg = inputs()[0].manufacturing
    quality = mfg.quality_attributes[0].model_dump(mode="python")
    quality["state"] = "verified"
    with pytest.raises(ValidationError, match="numeric acceptance limits"):
        type(mfg.quality_attributes[0]).model_validate(quality)
    potency = mfg.potency_strategy.model_dump(mode="python")
    potency["state"] = "verified"
    with pytest.raises(ValidationError, match="validated acceptance criteria"):
        type(mfg.potency_strategy).model_validate(potency)


def test_coa_rejects_cross_lot_results():
    workspace = inputs()[0]
    mfg = workspace.manufacturing
    refs = mfg.potency_strategy.refs
    lot1 = ManufacturingLot(lot_id="lot-real-1", process_version="v1", manufacture_date=date(2026, 1, 1),
        material_type="test material", manufacturing_state="verified", testing_state="verified",
        release_disposition="released", refs=refs)
    lot2 = lot1.model_copy(update={"lot_id": "lot-real-2"})
    result = ManufacturingTestResult(result_id="result-real-1", lot_id=lot1.lot_id,
        method_id=mfg.test_methods[0].method_id, specification_id=mfg.specifications[0].specification_id,
        attribute="identity", value="traceable value", tested_at=datetime(2026, 1, 2, tzinfo=timezone.utc), refs=refs)
    coa = CoaRecord(coa_id="coa-real-2", lot_id=lot2.lot_id, version="1",
        approval_state="approved", result_ids=[result.result_id], method_ids=[result.method_id],
        specification_ids=[result.specification_id], release_disposition="released",
        source_record_ids=["source-coa-real-2"])
    payload = mfg.model_dump(mode="python")
    payload.update(lots=[lot1, lot2], test_results=[result], coa_records=[coa])
    with pytest.raises(ValidationError, match="cross-lot"):
        type(mfg).model_validate(payload)


def test_stability_does_not_accept_verified_shelf_life_without_value():
    with pytest.raises(ValidationError, match="verified shelf life"):
        StabilityProgram(stability_program_id="stability-real-1", lot_ids=["lot-real-1"],
            state="in_development", shelf_life_state="verified", verified_shelf_life=None,
            refs=inputs()[0].manufacturing.potency_strategy.refs)


def test_unsupported_or_unapproved_update_preserves_every_manufacturing_record():
    workspace, state, agenda, docket, history = inputs()
    current = workspace.manufacturing
    refs = current.potency_strategy.refs
    lot = ManufacturingLot(lot_id="lot-unaccepted", process_version="unaccepted-v1",
        manufacture_date=date(2026, 1, 1), material_type="unaccepted material",
        manufacturing_state="verified", testing_state="verified", release_disposition="released",
        stability_program_ids=["stability-unaccepted"], refs=refs)
    result = ManufacturingTestResult(result_id="result-unaccepted", lot_id=lot.lot_id,
        method_id=current.test_methods[0].method_id,
        specification_id=current.specifications[0].specification_id,
        attribute="unaccepted attribute", value="unaccepted value",
        tested_at=datetime(2026, 1, 2, tzinfo=timezone.utc), refs=refs)
    stability = StabilityProgram(stability_program_id="stability-unaccepted", lot_ids=[lot.lot_id],
        state="verified", conditions=["private unaccepted condition"],
        attributes=["unaccepted attribute"],
        timepoints=[StabilityTimepoint(timepoint_id="timepoint-unaccepted", label="unaccepted", result_ids=[result.result_id])],
        shelf_life_state="verified", verified_shelf_life="unaccepted shelf life", refs=refs)
    coa = CoaRecord(coa_id="coa-unaccepted", lot_id=lot.lot_id, version="unaccepted",
        approval_state="approved", result_ids=[result.result_id], method_ids=[result.method_id],
        specification_ids=[result.specification_id], release_disposition="released",
        source_record_ids=["source-unaccepted"])
    payload = current.model_dump(mode="python")
    payload["product_definition"]["state"] = "verified"
    payload["readiness"][0]["state"] = "verified"
    payload["test_methods"][0]["state"] = "verified"
    payload["test_methods"][0]["validation_status"] = "verified"
    payload["specifications"][0]["approval_state"] = "approved"
    payload["specifications"][0]["acceptance_criteria"] = ["unaccepted criterion"]
    payload.update(lots=[lot], test_results=[result], stability_programs=[stability], coa_records=[coa])
    proposed = type(current).model_validate(payload)
    arguments = dict(state=state, agenda=agenda, docket=docket, history=history)
    assert apply_validated_manufacturing_update(workspace, proposed,
        verification_supports_state_change=False, human_approved=True, **arguments) is workspace
    assert apply_validated_manufacturing_update(workspace, proposed,
        verification_supports_state_change=True, human_approved=False, **arguments) is workspace
    assert workspace.manufacturing.product_definition.state == "proposed"
    assert workspace.manufacturing.test_methods[0].state == "proposed"
    assert workspace.manufacturing.test_methods[0].validation_status == "not_defined"
    assert workspace.manufacturing.readiness[0].state == "proposed"
    assert workspace.manufacturing.lots == workspace.manufacturing.test_results == []
    assert workspace.manufacturing.stability_programs == workspace.manufacturing.coa_records == []
    assert workspace.manufacturing.specifications[0].approval_state == "proposed"


def test_supported_update_still_rejects_unknown_evidence():
    workspace, state, agenda, docket, history = inputs()
    proposed = workspace.manufacturing.model_copy(deep=True)
    proposed.next_actions[0].refs.evidence_ids.append("invented-evidence")
    with pytest.raises(ValueError, match="unknown scientific evidence"):
        apply_validated_manufacturing_update(workspace, proposed,
            verification_supports_state_change=True, human_approved=True,
            state=state, agenda=agenda, docket=docket, history=history)


def test_unknown_matter_and_run_references_are_rejected():
    workspace, _, _, docket, history = inputs()
    proposed = workspace.manufacturing.model_copy(deep=True)
    proposed.next_actions[0].refs.matter_ids.append("invented-matter")
    proposed.next_actions[0].refs.run_ids.append("invented-run")
    with pytest.raises(ValueError, match="unknown docket matters"):
        validate_manufacturing_operational_refs(proposed, docket, history)


def test_public_manufacturing_is_sanitized_and_flagship_is_compact():
    workspace = inputs()[0]
    public = export_manufacturing(workspace.manufacturing)
    payload = public.model_dump(mode="json", by_alias=True)
    text = json.dumps(payload)
    assert payload["counts"] == {
        "realLots": 0, "testResults": 0, "proposedSpecifications": 1,
        "approvedReleaseSpecifications": 0, "validatedPotencyAssays": 0,
        "stabilityPrograms": 0, "verifiedShelfLifeRecords": 0, "coaRecords": 0,
    }
    assert payload["verifiedPublicLots"] == payload["verifiedPublicCoas"] == []
    assert payload["stabilityStatus"] == "evidence_gap"
    assert "proprietaryDetails" not in text and "deviations" not in text and "sourceRecordIds" not in text
    complete = build_current_public_state(ROOT)
    assert complete.manufacturing == public
    summary = complete.flagship_program.manufacturing
    assert summary.product_definition_state == "proposed"
    assert summary.potency_state == summary.reproducibility_state == summary.stability_state == "evidence_gap"
    assert complete.manufacturing.product_definition.drug_substance_identity is None
    assert len(complete.flagship_program.model_dump(mode="json", by_alias=True)["manufacturing"]) == 7


def test_public_manufacturing_references_only_canonical_state():
    workspace, state, _, _, history = inputs()
    public = export_manufacturing(workspace.manufacturing)
    assert set(public.potency.refs.evidence_ids) <= {item.evidence_id for item in state.evidence}
    assert set(public.potency.refs.claim_ids) <= {item.claim_id for item in state.claims}
    assert public.latest_relevant_determination_id in {
        f"signalrb-{run.run_id}" for run in history.runs
    }
