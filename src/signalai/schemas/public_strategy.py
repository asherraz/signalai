"""Frontend-safe product architecture strategy contract."""

from datetime import datetime

from pydantic import Field

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel
from signalai.schemas.product_strategy import (
    ArchitectureDimension, ProductArchitectureCandidate, StrategyDetermination,
    StrategyAssessmentHistoryEntry, TherapeuticObjective,
)


class PublicStrategyDimension(SignalModel):
    dimension: ArchitectureDimension
    title: NonEmptyText
    weight: int
    description: NonEmptyText


class PublicProductStrategy(SignalModel):
    program_id: Identifier = Field(alias="programId")
    therapeutic_objective: TherapeuticObjective = Field(alias="therapeuticObjective")
    current_provisional_lead: Identifier | None = Field(alias="currentProvisionalLead")
    recommendation_status: NonEmptyText = Field(alias="recommendationStatus")
    human_review_status: NonEmptyText = Field(alias="humanReviewStatus")
    last_assessed_at: datetime = Field(alias="lastAssessedAt")
    scoring_explanation: NonEmptyText = Field(alias="scoringExplanation")
    disclaimer: NonEmptyText
    dimensions: list[PublicStrategyDimension]
    candidate_leaderboard: list[Identifier] = Field(alias="candidateLeaderboard")
    candidates: list[ProductArchitectureCandidate]
    score_change_history: list[StrategyAssessmentHistoryEntry] = Field(alias="scoreChangeHistory")
    current_council_review: StrategyDetermination = Field(alias="currentCouncilReview")

