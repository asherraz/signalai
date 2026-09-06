"""Persistent therapeutic-development agenda contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class AgendaItemType(StrEnum):
    UNRESOLVED_SCIENTIFIC_QUESTION = "unresolved_scientific_question"
    ACTIVE_HYPOTHESIS = "active_hypothesis"
    OPEN_TRANSLATIONAL_RISK = "open_translational_risk"
    FORMULATION_QUESTION = "formulation_question"
    EXPERIMENT_PROPOSAL = "experiment_proposal"
    PENDING_DECISION = "pending_decision"
    EVIDENCE_GAP = "evidence_gap"
    JURISDICTION_QUESTION = "jurisdiction_question"


class AgendaPriority(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class AgendaStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


class AgendaItem(SignalModel):
    agenda_item_id: Identifier
    type: AgendaItemType
    question: NonEmptyText
    priority: AgendaPriority
    rationale: NonEmptyText
    linked_claim_ids: list[Identifier] = Field(default_factory=list)
    linked_evidence_ids: list[Identifier] = Field(default_factory=list)
    linked_hypothesis_ids: list[Identifier] = Field(default_factory=list)
    linked_risk_ids: list[Identifier] = Field(default_factory=list)
    status: AgendaStatus = AgendaStatus.OPEN
    created_at: datetime
    last_evaluated_at: datetime | None = None
    resolution: str | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> AgendaItem:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        if self.last_evaluated_at is not None:
            object.__setattr__(
                self,
                "last_evaluated_at",
                _require_timezone(self.last_evaluated_at, "last_evaluated_at"),
            )
        if self.status == AgendaStatus.RESOLVED and not self.resolution:
            raise ValueError("resolved agenda items require a resolution")
        if self.status != AgendaStatus.RESOLVED and self.resolution is not None:
            raise ValueError("resolution is only valid for resolved agenda items")
        return self


class DevelopmentAgenda(SignalModel):
    program_id: Identifier
    version: str = "1.0"
    updated_at: datetime
    items: list[AgendaItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_agenda(self) -> DevelopmentAgenda:
        object.__setattr__(
            self, "updated_at", _require_timezone(self.updated_at, "updated_at")
        )
        item_ids = [item.agenda_item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("agenda contains duplicate item IDs")
        return self
