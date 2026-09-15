"""Decision-oriented public program projection; not a scientific state mutation."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class FlagshipSourceRefs(SignalModel):
    claim_ids: list[Identifier] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    risk_ids: list[Identifier] = Field(default_factory=list)
    hypothesis_ids: list[Identifier] = Field(default_factory=list)
    review_ids: list[Identifier] = Field(default_factory=list)
    program_fields: list[NonEmptyText] = Field(default_factory=list)


class PublicDevelopmentGate(SignalModel):
    gate_id: Identifier
    name: NonEmptyText
    status: Literal["supported", "partially_defined", "unresolved", "blocked", "human_decision"]
    why_it_matters: NonEmptyText
    what_is_known: list[NonEmptyText] = Field(default_factory=list)
    what_is_missing: list[NonEmptyText] = Field(default_factory=list)
    next_action: str | None = None
    sources: FlagshipSourceRefs


class PublicPivotCriterion(SignalModel):
    criterion_id: Identifier
    condition: NonEmptyText
    review_id: Identifier
    evidence_ids: list[Identifier] = Field(default_factory=list)


class PublicProgramHistoryEntry(SignalModel):
    date: datetime
    matter_title: NonEmptyText
    determination_type: NonEmptyText
    state_change: NonEmptyText
    review_id: Identifier
    run_id: Identifier

    @model_validator(mode="after")
    def validate_date(self):
        object.__setattr__(self, "date", _require_timezone(self.date, "date"))
        return self


class PublicFlagshipThesis(SignalModel):
    biology: str | None = None
    product_hypothesis: str | None = None
    route: str | None = None
    development_hypothesis: str | None = None
    development_question: str | None = None
    sources: FlagshipSourceRefs


class PublicFlagshipProgram(SignalModel):
    program_id: Identifier = Field(alias="programId")
    name: NonEmptyText
    display_name: NonEmptyText = Field(alias="displayName")
    subtitle: NonEmptyText
    one_line_thesis: NonEmptyText = Field(alias="oneLineThesis")
    thesis: PublicFlagshipThesis
    status: NonEmptyText
    current_determination: str | None = Field(default=None, alias="currentDetermination")
    strongest_case_for: str | None = Field(default=None, alias="strongestCaseFor")
    strongest_case_against: str | None = Field(default=None, alias="strongestCaseAgainst")
    human_decision_required: bool = Field(alias="humanDecisionRequired")
    verification_status: str | None = Field(default=None, alias="verificationStatus")
    current_blockers: list[NonEmptyText] = Field(default_factory=list, alias="currentBlockers")
    development_gates: list[PublicDevelopmentGate] = Field(alias="developmentGates")
    current_next_action: str | None = Field(default=None, alias="currentNextAction")
    pivot_question: Literal["What would make Signal change its mind?"] = Field(default="What would make Signal change its mind?", alias="pivotQuestion")
    pivot_criteria: list[PublicPivotCriterion] = Field(default_factory=list, alias="pivotCriteria")
    signal_rb_review_id: Identifier | None = Field(default=None, alias="signalRBReviewId")
    evidence_confidence: str | None = Field(default=None, alias="evidenceConfidence")
    updated_at: datetime = Field(alias="updatedAt")
    program_history: list[PublicProgramHistoryEntry] = Field(default_factory=list, alias="programHistory")
    sources: FlagshipSourceRefs

    @model_validator(mode="after")
    def validate_projection(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        gates = [g.gate_id for g in self.development_gates]
        runs = [h.run_id for h in self.program_history]
        if len(gates) != len(set(gates)) or len(runs) != len(set(runs)):
            raise ValueError("flagship gates and history must be deduplicated")
        if self.program_history != sorted(self.program_history, key=lambda h: (h.date, h.run_id)):
            raise ValueError("programHistory must be chronological")
        return self
