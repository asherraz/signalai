"""Structured outputs for one autonomous daily reasoning cycle."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from signalai.schemas.agenda import AgendaItem, AgendaStatus
from signalai.schemas.models import (
    Claim,
    Decision,
    Hypothesis,
    Identifier,
    NonEmptyText,
    Risk,
    EvidenceConfidence,
    ProgramStatus,
    SignalModel,
    _require_timezone,
)


class SelectedTask(SignalModel):
    item: AgendaItem
    selection_reason: NonEmptyText


class DailyAnalysis(SignalModel):
    agenda_item_id: Identifier
    objective: NonEmptyText
    assessment: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    claim_ids: list[Identifier] = Field(default_factory=list)
    proposed_next_action: str | None = None
    supports_material_change: bool


class DailyCritique(SignalModel):
    agenda_item_id: Identifier
    challenge: NonEmptyText
    limitations: list[NonEmptyText] = Field(min_length=1)
    evidence_ids: list[Identifier] = Field(default_factory=list)


class DailySynthesis(SignalModel):
    agenda_item_id: Identifier
    material_change: bool
    rationale: NonEmptyText
    claim_updates: list[Claim] = Field(default_factory=list)
    hypothesis_update: Hypothesis | None = None
    risk_updates: list[Risk] = Field(default_factory=list)
    decision_proposal: Decision | None = None
    evidence_confidence_update: EvidenceConfidence | None = None
    program_status_update: ProgramStatus | None = None
    next_action: str | None = None
    agenda_status: AgendaStatus
    agenda_resolution: str | None = None
    what_changed: NonEmptyText

    @model_validator(mode="after")
    def validate_change_claim(self) -> DailySynthesis:
        scientific_updates = bool(
            self.claim_updates
            or self.hypothesis_update
            or self.risk_updates
            or self.decision_proposal
            or self.evidence_confidence_update
            or self.program_status_update
        )
        if not self.material_change and scientific_updates:
            raise ValueError("no-material-change synthesis cannot contain scientific updates")
        if self.agenda_status == AgendaStatus.RESOLVED and not self.agenda_resolution:
            raise ValueError("resolved agenda synthesis requires a resolution")
        if self.agenda_status != AgendaStatus.RESOLVED and self.agenda_resolution is not None:
            raise ValueError("agenda_resolution is only valid when resolving an item")
        if self.decision_proposal is not None:
            decision = self.decision_proposal
            if decision.requires_human_approval and decision.approval_status.value != "pending":
                raise ValueError("human-gated daily decisions must remain pending approval")
        return self


class WhatChanged(SignalModel):
    run_id: Identifier
    agenda_item_id: Identifier
    material_change: bool
    summary: NonEmptyText
    created_at: datetime

    @model_validator(mode="after")
    def validate_created_at(self) -> WhatChanged:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        return self
