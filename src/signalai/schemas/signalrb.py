"""Canonical, conclusion-only Signal Review Board contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


DeterminationType = Literal[
    "state_updated", "no_material_change", "human_decision_required", "evidence_gap", "blocked", "not_recorded"
]


class SignalReviewBoardDetermination(SignalModel):
    review_id: Identifier
    run_id: Identifier
    program_id: Identifier
    matter_id: Identifier
    matter_title: NonEmptyText
    matter_question: NonEmptyText
    domain: NonEmptyText
    reviewers: list[NonEmptyText] = Field(min_length=1)
    strongest_case_for: NonEmptyText
    strongest_case_against: NonEmptyText
    verification_status: Literal["verified", "unsupported_assertions", "not_recorded"]
    determination: NonEmptyText
    determination_type: DeterminationType
    conditions: list[NonEmptyText] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    state_change: bool | Literal["not_recorded"]
    human_decision_required: bool
    next_action: NonEmptyText
    created_at: datetime

    @model_validator(mode="after")
    def validate_review(self):
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        if self.determination_type == "no_material_change" and self.state_change is True:
            raise ValueError("no_material_change cannot contain a scientific state change")
        if self.determination_type == "human_decision_required" and not self.human_decision_required:
            raise ValueError("human determination must preserve the approval gate")
        if self.state_change is True and not self.evidence_ids:
            raise ValueError("scientific state change requires evidence provenance")
        return self


class PublicPendingBoardDecision(SignalModel):
    decision_id: Identifier
    program_id: Identifier
    question: NonEmptyText
    outcome: str | None = None
    approval_status: str
    evidence_ids: list[Identifier] = Field(default_factory=list)


class PublicSignalRB(SignalModel):
    name: Literal["SignalRB"] = "SignalRB"
    label: Literal["Signal Review Board"] = "Signal Review Board"
    latest_review: SignalReviewBoardDetermination | None = Field(default=None, alias="latestReview")
    recent_reviews: list[SignalReviewBoardDetermination] = Field(default_factory=list, alias="recentReviews")
    pending_human_decisions: list[PublicPendingBoardDecision] = Field(default_factory=list, alias="pendingHumanDecisions")
    summary: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_history(self):
        ids = [r.run_id for r in self.recent_reviews]
        if len(ids) != len(set(ids)):
            raise ValueError("SignalRB reviews must be deduplicated by run")
        if self.latest_review and self.recent_reviews and self.latest_review != self.recent_reviews[0]:
            raise ValueError("latestReview must match the newest review")
        return self
