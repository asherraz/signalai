"""Typed scientific-state and run-provenance schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]
NonEmptyText = Annotated[str, Field(min_length=1)]


class SignalModel(BaseModel):
    """Strict base model shared by all persisted SignalAI records."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class ProgramStatus(StrEnum):
    DISCOVERY = "discovery"
    PRECLINICAL = "preclinical"
    CLINICAL = "clinical"
    PAUSED = "paused"
    TERMINATED = "terminated"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    RETRACTED = "retracted"


class EvidenceKind(StrEnum):
    PUBLICATION = "publication"
    DATASET = "dataset"
    EXPERIMENT = "experiment"
    REGULATORY = "regulatory"
    PATENT = "patent"
    OTHER = "other"


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class RiskStatus(StrEnum):
    OPEN = "open"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    CLOSED = "closed"


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TherapeuticProgram(SignalModel):
    program_id: Identifier
    name: NonEmptyText
    asset_name: NonEmptyText
    modality: NonEmptyText
    route_of_administration: NonEmptyText
    indication: str | None = None
    status: ProgramStatus = ProgramStatus.DISCOVERY
    claim_ids: list[Identifier] = Field(default_factory=list)
    hypothesis_ids: list[Identifier] = Field(default_factory=list)
    risk_ids: list[Identifier] = Field(default_factory=list)
    decision_ids: list[Identifier] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_timestamps(self) -> TherapeuticProgram:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class Evidence(SignalModel):
    evidence_id: Identifier
    kind: EvidenceKind
    title: NonEmptyText
    source_uri: HttpUrl | None = None
    source_identifier: str | None = None
    locator: str | None = None
    excerpt: str | None = None
    retrieved_at: datetime
    content_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provenance(self) -> Evidence:
        object.__setattr__(
            self, "retrieved_at", _require_timezone(self.retrieved_at, "retrieved_at")
        )
        if self.source_uri is None and not self.source_identifier:
            raise ValueError("source_uri or source_identifier is required")
        return self


class Claim(SignalModel):
    claim_id: Identifier
    program_id: Identifier
    statement: NonEmptyText
    status: ClaimStatus = ClaimStatus.PROPOSED
    evidence_ids: Annotated[list[Identifier], Field(min_length=1)]
    rationale: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_created_at(self) -> Claim:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        return self


class Hypothesis(SignalModel):
    hypothesis_id: Identifier
    program_id: Identifier
    statement: NonEmptyText
    rationale: NonEmptyText
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    supporting_claim_ids: list[Identifier] = Field(default_factory=list)
    contradicting_claim_ids: list[Identifier] = Field(default_factory=list)
    test_plan: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_created_at(self) -> Hypothesis:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        return self


class Risk(SignalModel):
    risk_id: Identifier
    program_id: Identifier
    title: NonEmptyText
    description: NonEmptyText
    probability: Annotated[float, Field(ge=0, le=1)]
    impact: Annotated[int, Field(ge=1, le=5)]
    status: RiskStatus = RiskStatus.OPEN
    evidence_ids: list[Identifier] = Field(default_factory=list)
    mitigation: str | None = None
    owner: str | None = None


class Decision(SignalModel):
    decision_id: Identifier
    program_id: Identifier
    question: NonEmptyText
    outcome: str | None = None
    rationale: str | None = None
    supporting_claim_ids: list[Identifier] = Field(default_factory=list)
    risk_ids: list[Identifier] = Field(default_factory=list)
    requires_human_approval: bool = True
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str | None = None
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_approval(self) -> Decision:
        if self.approved_at is not None:
            object.__setattr__(
                self, "approved_at", _require_timezone(self.approved_at, "approved_at")
            )
        if self.requires_human_approval:
            if self.approval_status == ApprovalStatus.NOT_REQUIRED:
                raise ValueError("approval cannot be not_required when human approval is required")
        elif self.approval_status != ApprovalStatus.NOT_REQUIRED:
            raise ValueError("approval_status must be not_required when approval is not required")
        if self.approval_status == ApprovalStatus.APPROVED:
            if not self.approved_by or self.approved_at is None:
                raise ValueError("approved decisions require approved_by and approved_at")
        elif self.approved_by is not None or self.approved_at is not None:
            raise ValueError("approval identity and timestamp are only valid for approved decisions")
        return self


class AgentRun(SignalModel):
    run_id: Identifier
    agent_name: NonEmptyText
    program_id: Identifier | None = None
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parent_run_id: Identifier | None = None
    resume_from_run_id: Identifier | None = None
    input_artifact_paths: list[str] = Field(default_factory=list)
    intermediate_artifact_paths: list[str] = Field(default_factory=list)
    output_artifact_paths: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> AgentRun:
        if self.started_at is not None:
            object.__setattr__(
                self, "started_at", _require_timezone(self.started_at, "started_at")
            )
        if self.completed_at is not None:
            object.__setattr__(
                self, "completed_at", _require_timezone(self.completed_at, "completed_at")
            )
        if self.completed_at is not None and self.started_at is None:
            raise ValueError("completed_at requires started_at")
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        terminal = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
        if self.status in terminal and self.completed_at is None:
            raise ValueError("terminal runs require completed_at")
        if self.status == RunStatus.FAILED and not self.error:
            raise ValueError("failed runs require an error")
        if self.status != RunStatus.FAILED and self.error is not None:
            raise ValueError("error is only valid for failed runs")
        return self


class ClaimSet(SignalModel):
    """Validated output of the research stage."""

    claims: Annotated[list[Claim], Field(min_length=1)]


class HypothesisProposal(SignalModel):
    """Validated output of the hypothesis stage."""

    hypothesis: Hypothesis


class Critique(SignalModel):
    """A structured challenge to a proposed development hypothesis."""

    hypothesis_id: Identifier
    summary: NonEmptyText
    challenges: Annotated[list[NonEmptyText], Field(min_length=1)]
    evidence_ids: list[Identifier] = Field(default_factory=list)


class CritiqueResult(SignalModel):
    """Validated output of the critic stage."""

    critique: Critique


class DecisionProposal(SignalModel):
    """Validated output of the synthesis stage."""

    decision: Decision


class SignalState(SignalModel):
    """Complete validated internal or public state for one development run."""

    schema_version: str = "1.0"
    run_id: Identifier
    generated_at: datetime
    program: TherapeuticProgram
    evidence: Annotated[list[Evidence], Field(min_length=1)]
    claims: Annotated[list[Claim], Field(min_length=1)]
    hypothesis: Hypothesis
    critique: Critique
    decision: Decision

    @model_validator(mode="after")
    def validate_generated_at(self) -> SignalState:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        if self.program.program_id != "SGL-001":
            raise ValueError("Milestone 1 state must describe SGL-001")
        evidence_ids = {item.evidence_id for item in self.evidence}
        claim_ids = {item.claim_id for item in self.claims}
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("state contains duplicate evidence IDs")
        if len(claim_ids) != len(self.claims):
            raise ValueError("state contains duplicate claim IDs")
        for claim in self.claims:
            if claim.program_id != self.program.program_id:
                raise ValueError("state claim belongs to a different program")
            if set(claim.evidence_ids) - evidence_ids:
                raise ValueError("state claim references unknown evidence")
        if set(self.program.claim_ids) != claim_ids:
            raise ValueError("program claim IDs do not match state claims")
        if self.hypothesis.hypothesis_id not in self.program.hypothesis_ids:
            raise ValueError("program does not reference the state hypothesis")
        hypothesis_claim_ids = set(
            self.hypothesis.supporting_claim_ids + self.hypothesis.contradicting_claim_ids
        )
        if hypothesis_claim_ids - claim_ids:
            raise ValueError("state hypothesis references unknown claims")
        if self.critique.hypothesis_id != self.hypothesis.hypothesis_id:
            raise ValueError("state critique references a different hypothesis")
        if set(self.critique.evidence_ids) - evidence_ids:
            raise ValueError("state critique references unknown evidence")
        if self.decision.decision_id not in self.program.decision_ids:
            raise ValueError("program does not reference the state decision")
        if set(self.decision.supporting_claim_ids) - claim_ids:
            raise ValueError("state decision references unknown claims")
        return self
