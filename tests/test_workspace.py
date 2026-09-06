import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.schemas import (
    DevelopmentAgenda,
    FormulationScore,
    PublicCargoState,
    PublicExcipientCandidate,
    SignalState,
    TherapeuticAssetWorkspace,
)
from signalai.workspace_export import export_workspace, validate_workspace_references


ROOT = Path(__file__).resolve().parents[1]


def _workspace() -> TherapeuticAssetWorkspace:
    return TherapeuticAssetWorkspace.model_validate_json(
        (ROOT / "state" / "asset-development.json").read_text(encoding="utf-8")
    )


def test_workspace_models_and_cross_references_validate() -> None:
    workspace = _workspace()
    state = SignalState.model_validate_json(
        (ROOT / "state" / "signal-state.json").read_text(encoding="utf-8")
    )
    agenda = DevelopmentAgenda.model_validate_json(
        (ROOT / "state" / "development-agenda.json").read_text(encoding="utf-8")
    )

    validate_workspace_references(workspace, state, agenda)
    assert workspace.program_id == "SGL-001"
    assert workspace.cargo.operator_focus_candidate_ids == ["cargo-native-msc-ev-secretome"]


def test_unknown_scientific_reference_is_rejected() -> None:
    workspace = _workspace()
    state = SignalState.model_validate_json(
        (ROOT / "state" / "signal-state.json").read_text(encoding="utf-8")
    )
    agenda = DevelopmentAgenda.model_validate_json(
        (ROOT / "state" / "development-agenda.json").read_text(encoding="utf-8")
    )
    payload = workspace.model_dump(mode="python")
    payload["cargo"]["candidates"][0]["evidence_ids"].append("evidence-does-not-exist")
    invalid = TherapeuticAssetWorkspace.model_validate(payload)

    with pytest.raises(ValueError, match="unknown scientific evidence"):
        validate_workspace_references(invalid, state, agenda)


def test_formulation_total_is_inspectable_ordinal_sum() -> None:
    score = _workspace().formulation.candidates[0].score
    assert score.total_score == 6
    payload = score.model_dump(mode="python")
    payload["total_score"] = 9

    with pytest.raises(ValidationError, match="ordinal component sum"):
        FormulationScore.model_validate(payload)


def test_cargo_pathway_counts_are_derived_from_links() -> None:
    cargo, _, _ = export_workspace(_workspace())
    counts = {pathway.id: pathway.candidate_count for pathway in cargo.pathways}

    assert counts == {"pathway-neuroinflammation": 3, "pathway-neural-plasticity": 1}
    assert cargo.focus_candidates == ["cargo-native-msc-ev-secretome"]
    assert len(cargo.benchmarks) == 2


def test_excluded_candidates_require_a_reason() -> None:
    candidate = _workspace().cargo.candidates[0].model_dump(mode="python")
    candidate.update(development_status="excluded", exclusion_reason=None)

    with pytest.raises(ValidationError, match="require exclusion_reason"):
        type(_workspace().cargo.candidates[0]).model_validate(candidate)


def test_jurisdictions_require_source_provenance() -> None:
    jurisdiction = _workspace().jurisdictions.jurisdictions[0].model_dump(mode="python")
    jurisdiction["source_document_ids"] = []

    with pytest.raises(ValidationError):
        type(_workspace().jurisdictions.jurisdictions[0]).model_validate(jurisdiction)


def test_public_workspace_serialization_and_missing_optional_data() -> None:
    cargo, formulation, jurisdictions = export_workspace(_workspace())
    cargo_payload = cargo.model_dump(mode="json", by_alias=True)
    formulation_payload = formulation.model_dump(mode="json", by_alias=True)
    jurisdiction_payload = jurisdictions.model_dump(mode="json", by_alias=True)

    assert PublicCargoState.model_validate(cargo_payload) == cargo
    assert "operatorFocusCandidateIds" in cargo_payload
    assert formulation_payload["excipients"][0]["proposedConcentration"] is None
    assert jurisdiction_payload["summaryCounts"]["restrictive"] == 1
    assert jurisdiction_payload["summaryCounts"]["unresolved"] == 1

    minimal_excipient = {
        "id": "excipient-minimal",
        "name": "Unspecified candidate",
        "functionalRole": "stability",
        "evCompatibility": "not_assessed",
        "intranasalPrecedent": "not_assessed",
        "humanPrecedent": "not_assessed",
        "regulatoryPrecedent": "not_assessed",
        "formulationValue": "not_assessed",
        "risk": "Not assessed.",
        "evidenceIds": [],
        "status": "candidate"
    }
    assert PublicExcipientCandidate.model_validate(minimal_excipient).proposed_concentration is None


def test_canonical_workspace_is_valid_json() -> None:
    payload = json.loads((ROOT / "state" / "asset-development.json").read_text())
    assert set(payload) == {"schema_version", "program_id", "generated_at", "cargo", "formulation", "jurisdictions"}
