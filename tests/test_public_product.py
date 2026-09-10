import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.clinical_network import approve_public_listing
from signalai.clinical_network_export import export_clinical_network
from signalai.product_export import export_product_layer
from signalai.schemas import (
    AccessTier,
    Clinic,
    ClinicalNetworkState,
    PartnerRole,
    PublicAccessDefinition,
    PublicChange,
    PublicSignalState,
    SignalState,
    TherapeuticAssetWorkspace,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _inputs():
    scientific = SignalState.model_validate_json(
        (ROOT / "state" / "signal-state.json").read_text(encoding="utf-8")
    )
    workspace = TherapeuticAssetWorkspace.model_validate_json(
        (ROOT / "state" / "asset-development.json").read_text(encoding="utf-8")
    )
    clinical = ClinicalNetworkState.model_validate_json(
        (ROOT / "state" / "clinical-network.json").read_text(encoding="utf-8")
    )
    existing_public = PublicSignalState.model_validate_json(
        (ROOT / "public" / "signal-state.json").read_text(encoding="utf-8")
    )
    public_network = export_clinical_network(
        clinical,
        scientific,
        workspace,
        what_changed_recently=existing_public.changes[0].summary,
    )
    return scientific, workspace, clinical, existing_public, public_network


def _export():
    scientific, workspace, clinical, existing_public, public_network = _inputs()
    return export_product_layer(
        scientific,
        workspace,
        clinical,
        public_network,
        changes=existing_public.changes,
        latest_run=existing_public.latest_run,
    )


def test_intelligence_modules_derive_from_real_state() -> None:
    product, _ = _export()
    scientific, workspace, _, _, _ = _inputs()
    modules = {item.module_id: item for item in product.intelligence.modules}

    assert set(modules) == {
        "therapeutic-programs",
        "cargo",
        "formulation",
        "jurisdictions",
        "evidence",
        "airb",
        "exosome-product-review",
    }
    assert modules["cargo"].key_metrics["candidates"] == len(workspace.cargo.candidates)
    assert modules["formulation"].key_metrics["excipients"] == len(
        workspace.formulation.excipients
    )
    assert modules["evidence"].key_metrics["evidenceRecords"] == len(
        scientific.evidence
    )
    assert scientific.decision.decision_id in modules["airb"].partner_intelligence.reference_ids


def test_access_tiers_and_public_partner_separation_validate() -> None:
    product, _ = _export()
    assert [item.tier for item in product.access.tiers] == [
        AccessTier.PUBLIC,
        AccessTier.PARTNER,
        AccessTier.PRO,
    ]
    assert product.access.authentication_enabled is False
    assert product.access.billing_enabled is False
    for module in product.intelligence.modules:
        assert module.public_preview
        assert module.partner_intelligence.summary
        assert module.partner_intelligence.access_tier is AccessTier.PARTNER

    with pytest.raises(ValidationError):
        PublicAccessDefinition(
            tier="subscriber",
            title="Invalid",
            description="Not a supported tier.",
            currentlyEnforcedServerSide=False,
        )


def test_network_summary_uses_only_approved_public_clinics() -> None:
    scientific, workspace, _, existing_public, _ = _inputs()
    private = Clinic(
        clinic_id="clinic-private",
        name="Private Test Clinic",
        city="Test City",
        country="Test Country",
        region="Test Region",
        contact_email="private@example.org",
        created_at=NOW,
        updated_at=NOW,
    )
    approved = approve_public_listing(
        Clinic(
            clinic_id="clinic-public",
            name="Public Test Clinic",
            city="Public City",
            country="Public Country",
            region="Public Region",
            contact_email="hidden@example.org",
            created_at=NOW,
            updated_at=NOW,
        ),
        approved_by="human-reviewer",
        roles=[PartnerRole.LISTED_PARTNER],
        approved_at=NOW,
    )
    clinical = ClinicalNetworkState(generated_at=NOW, clinics=[private, approved])
    public_network = export_clinical_network(clinical, scientific, workspace)
    product, _ = export_product_layer(
        scientific,
        workspace,
        clinical,
        public_network,
        changes=existing_public.changes,
        latest_run=existing_public.latest_run,
    )
    serialized = product.network.model_dump_json(by_alias=True)

    assert product.network.approved_public_clinic_count == 1
    assert [item.clinic_id for item in product.network.public_clinic_cards] == [
        "clinic-public"
    ]
    assert "clinic-private" not in serialized
    assert "private@example.org" not in serialized
    assert "hidden@example.org" not in serialized


def test_feed_is_backed_by_existing_changes_and_run_artifacts() -> None:
    _, feed = _export()
    scientific, _, _, existing_public, _ = _inputs()
    assert existing_public.latest_run is not None
    assert {item.type.value for item in feed} == {
        "program_state_change",
        "airb_determination",
    }
    assert any(
        existing_public.changes[0].change_id in item.linked_artifact_ids for item in feed
    )
    assert any(scientific.decision.decision_id in item.linked_decision_ids for item in feed)


def test_programs_index_and_clinic_view_are_consistent() -> None:
    product, _ = _export()
    scientific, workspace, _, _, _ = _inputs()
    program = product.programs.programs[0]

    assert program.program_id == scientific.program.program_id
    assert program.current_hypothesis == scientific.hypothesis.statement
    assert program.current_airb_determination.decision_id == scientific.decision.decision_id
    assert program.interested_clinic_count == 0
    assert program.approved_clinic_partner_count == 0
    assert product.intelligence.clinic_view.personalization_status == "not_personalized"
    assert set(product.intelligence.clinic_view.relevant_jurisdiction_ids) == {
        item.jurisdiction_id for item in workspace.jurisdictions.jurisdictions
    }


def test_generated_payload_remains_backward_compatible_and_private_safe() -> None:
    payload = json.loads((ROOT / "public" / "signal-state.json").read_text(encoding="utf-8"))
    expected_existing = {
        "generatedAt",
        "version",
        "status",
        "program",
        "changes",
        "loop",
        "evidence",
        "hypotheses",
        "risks",
        "decisions",
        "currentHypothesis",
        "latestRun",
        "cargo",
        "formulation",
        "jurisdictions",
        "clinicalNetwork",
    }
    assert expected_existing <= set(payload)
    assert {"product", "intelligenceFeed"} <= set(payload)
    serialized = json.dumps({"product": payload["product"], "feed": payload["intelligenceFeed"]})
    assert "contact_email" not in serialized
    assert "contactEmail" not in serialized
