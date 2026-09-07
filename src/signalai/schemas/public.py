"""Strict public JSON contract consumed by the separate frontend."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from signalai.schemas.models import (
    Claim,
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
from signalai.schemas.public_artifacts import PublicHypothesisArtifact, PublicLatestRun
from signalai.schemas.public_clinical_network import PublicClinicalNetwork
from signalai.schemas.public_product import PublicIntelligenceFeedItem, PublicProduct
from signalai.schemas.public_workspace import (
    PublicCargoState,
    PublicFormulationState,
    PublicJurisdictionState,
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


class PublicProgram(TherapeuticProgram):
    """Program summary plus the validated claims omitted from the top-level contract."""

    claims: list[Claim] = Field(default_factory=list)


class PublicSignalState(SignalModel):
    """Frontend-facing projection with a stable, camel-cased top-level contract."""

    generated_at: datetime = Field(
        serialization_alias="generatedAt",
        validation_alias="generatedAt",
    )
    version: str
    status: PublicStateStatus
    program: PublicProgram
    changes: list[PublicChange] = Field(default_factory=list)
    loop: PublicLoop
    evidence: list[Evidence] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    current_hypothesis: PublicHypothesisArtifact | None = Field(
        default=None,
        serialization_alias="currentHypothesis",
        validation_alias="currentHypothesis",
    )
    latest_run: PublicLatestRun | None = Field(
        default=None,
        serialization_alias="latestRun",
        validation_alias="latestRun",
    )
    cargo: PublicCargoState | None = None
    formulation: PublicFormulationState | None = None
    jurisdictions: PublicJurisdictionState | None = None
    clinical_network: PublicClinicalNetwork | None = Field(
        default=None,
        alias="clinicalNetwork",
    )
    product: PublicProduct | None = None
    intelligence_feed: list[PublicIntelligenceFeedItem] = Field(
        default_factory=list,
        alias="intelligenceFeed",
    )

    @model_validator(mode="after")
    def validate_public_state(self) -> PublicSignalState:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        if self.program.program_id != "SGL-001":
            raise ValueError("Milestone 1 public state must describe SGL-001")
        return self

    @classmethod
    def from_internal(
        cls,
        state: SignalState,
        *,
        changes: list[PublicChange] | None = None,
        completed_stages: list[str] | None = None,
        current_hypothesis: PublicHypothesisArtifact | None = None,
        latest_run: PublicLatestRun | None = None,
        cargo: PublicCargoState | None = None,
        formulation: PublicFormulationState | None = None,
        jurisdictions: PublicJurisdictionState | None = None,
        clinical_network: PublicClinicalNetwork | None = None,
        product: PublicProduct | None = None,
        intelligence_feed: list[PublicIntelligenceFeedItem] | None = None,
    ) -> PublicSignalState:
        return cls(
            generatedAt=state.generated_at,
            version=state.schema_version,
            status=PublicStateStatus.AWAITING_HUMAN_REVIEW,
            program=PublicProgram(
                **state.program.model_dump(mode="python"),
                claims=state.claims,
            ),
            changes=changes or [
                PublicChange(
                    changeId=f"{state.run_id}-state-populated",
                    summary=(
                        "Clarified SGL-001's neuroregeneration/cognitive-function "
                        "development focus and replaced uncalibrated numeric risk "
                        "estimates with ordinal assessments."
                    ),
                )
            ],
            loop=PublicLoop(
                runId=state.run_id,
                status=RunStatus.SUCCEEDED,
                completedStages=completed_stages
                or ["research", "hypothesis", "critic", "synthesis"],
            ),
            evidence=state.evidence,
            hypotheses=[state.hypothesis],
            risks=state.risks,
            decisions=[state.decision],
            currentHypothesis=current_hypothesis,
            latestRun=latest_run,
            cargo=cargo,
            formulation=formulation,
            jurisdictions=jurisdictions,
            clinicalNetwork=clinical_network,
            product=product,
            intelligenceFeed=intelligence_feed or [],
        )
