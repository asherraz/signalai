from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from signalai.schemas import (
    AgentRun,
    ApprovalStatus,
    Claim,
    Decision,
    Evidence,
    EvidenceKind,
    Hypothesis,
    Risk,
    RiskLevel,
    RunStatus,
    TherapeuticProgram,
)


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def test_therapeutic_program_round_trips_as_json() -> None:
    program = TherapeuticProgram(
        program_id="SGL-001",
        name="SGL-001 development program",
        asset_name="SGL-001",
        modality="extracellular-vesicle/exosome therapeutic",
        route_of_administration="intranasal",
        created_at=NOW,
        updated_at=NOW,
    )

    assert TherapeuticProgram.model_validate_json(program.model_dump_json()) == program


def test_evidence_requires_traceable_source() -> None:
    with pytest.raises(ValidationError, match="source_uri or source_identifier"):
        Evidence(
            evidence_id="ev-1",
            kind=EvidenceKind.PUBLICATION,
            title="Source-free evidence",
            retrieved_at=NOW,
        )


def test_claim_requires_evidence_provenance() -> None:
    with pytest.raises(ValidationError):
        Claim(
            claim_id="claim-1",
            program_id="SGL-001",
            statement="A scientific assertion",
            evidence_ids=[],
        )


def test_hypothesis_is_distinct_from_supported_claims() -> None:
    hypothesis = Hypothesis(
        hypothesis_id="hyp-1",
        program_id="SGL-001",
        statement="Intranasal delivery may reach the target tissue.",
        rationale="The route merits experimental testing.",
        supporting_claim_ids=["claim-1"],
        test_plan="Evaluate biodistribution in a predefined model.",
    )

    assert hypothesis.status.value == "proposed"
    assert hypothesis.supporting_claim_ids == ["claim-1"]


def test_risk_uses_ordinal_likelihood_and_severity() -> None:
    risk = Risk(
        risk_id="risk-1",
        program_id="SGL-001",
        title="Translation risk",
        description="Delivery may not translate between species.",
        likelihood=RiskLevel.HIGH,
        severity=RiskLevel.CRITICAL,
    )

    assert risk.likelihood is RiskLevel.HIGH
    assert risk.severity is RiskLevel.CRITICAL


def test_risk_rejects_numeric_probability() -> None:
    with pytest.raises(ValidationError):
        Risk(
            risk_id="risk-1",
            program_id="SGL-001",
            title="Invalid risk",
            description="Numeric probabilities are not calibrated.",
            probability=1.1,
            likelihood="high",
            severity="critical",
        )


def test_approved_decision_requires_human_audit_fields() -> None:
    with pytest.raises(ValidationError, match="approved_by and approved_at"):
        Decision(
            decision_id="decision-1",
            program_id="SGL-001",
            question="Advance to the next development stage?",
            outcome="Advance",
            approval_status=ApprovalStatus.APPROVED,
        )


def test_approved_decision_retains_human_audit_fields() -> None:
    decision = Decision(
        decision_id="decision-approved",
        program_id="SGL-001",
        question="Advance to the next development stage?",
        outcome="Advance",
        approval_status=ApprovalStatus.APPROVED,
        approved_by="reviewer@example.org",
        approved_at=NOW,
    )

    assert decision.approved_by == "reviewer@example.org"
    assert decision.approved_at == NOW


def test_non_gated_decision_uses_not_required_status() -> None:
    decision = Decision(
        decision_id="decision-2",
        program_id="SGL-001",
        question="Regenerate a derived index?",
        requires_human_approval=False,
        approval_status=ApprovalStatus.NOT_REQUIRED,
    )

    assert decision.approval_status is ApprovalStatus.NOT_REQUIRED


def test_failed_run_preserves_error_and_resume_link() -> None:
    run = AgentRun(
        run_id="run-20260903-001",
        agent_name="future-agent",
        program_id="SGL-001",
        status=RunStatus.FAILED,
        started_at=NOW,
        completed_at=NOW,
        resume_from_run_id="run-20260903-000",
        intermediate_artifact_paths=["runs/run-20260903-001/checkpoint.json"],
        error="Synthetic test failure",
    )

    assert run.error == "Synthetic test failure"
    assert run.resume_from_run_id == "run-20260903-000"


def test_terminal_run_requires_completion_timestamp() -> None:
    with pytest.raises(ValidationError, match="terminal runs require completed_at"):
        AgentRun(
            run_id="run-1",
            agent_name="future-agent",
            status=RunStatus.SUCCEEDED,
            started_at=NOW,
        )


def test_schemas_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TherapeuticProgram(
            program_id="SGL-001",
            name="SGL-001 development program",
            asset_name="SGL-001",
            modality="extracellular vesicle",
            route_of_administration="intranasal",
            unexpected=True,
        )
