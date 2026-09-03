"""Strict public JSON contract consumed by the separate frontend."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from signalai.schemas.models import (
    Decision,
    Evidence,
    Hypothesis,
    Risk,
    RunStatus,
    SignalModel,
    SignalState,
    TherapeuticProgram,
    _require_timezone,
)


class PublicStateStatus(StrEnum):
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    APPROVED = "approved"


class PublicChange(SignalModel):
    change_id: str = Field(serialization_alias="changeId", validation_alias="changeId")
    summary: Annotated[str, Field(min_length=1)]


class PublicLoop(SignalModel):
    run_id: str = Field(serialization_alias="runId", validation_alias="runId")
    status: RunStatus
    completed_stages: list[str] = Field(
        serialization_alias="completedStages",
        validation_alias="completedStages",
    )


class PublicSignalState(SignalModel):
    """Frontend-facing projection with a stable, camel-cased top-level contract."""

    generated_at: datetime = Field(
        serialization_alias="generatedAt",
        validation_alias="generatedAt",
    )
    version: str
    status: PublicStateStatus
    program: TherapeuticProgram
    changes: list[PublicChange] = Field(default_factory=list)
    loop: PublicLoop
    evidence: list[Evidence] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_public_state(self) -> PublicSignalState:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        if self.program.program_id != "SGL-001":
            raise ValueError("Milestone 1 public state must describe SGL-001")
        return self

    @classmethod
    def from_internal(cls, state: SignalState) -> PublicSignalState:
        return cls(
            generatedAt=state.generated_at,
            version=state.schema_version,
            status=PublicStateStatus.AWAITING_HUMAN_REVIEW,
            program=state.program,
            changes=[],
            loop=PublicLoop(
                runId=state.run_id,
                status=RunStatus.SUCCEEDED,
                completedStages=["research", "hypothesis", "critic", "synthesis"],
            ),
            evidence=state.evidence,
            hypotheses=[state.hypothesis],
            risks=[],
            decisions=[state.decision],
        )
