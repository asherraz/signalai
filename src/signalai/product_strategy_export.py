"""Sanitized Product Strategy projection."""

from signalai.product_strategy import DIMENSION_TITLES
from signalai.schemas.product_strategy import ProductStrategyWorkspace
from signalai.schemas.public_strategy import PublicProductStrategy, PublicStrategyDimension


def export_product_strategy(value: ProductStrategyWorkspace) -> PublicProductStrategy:
    ranking = value.latest_determination.proposed_ranking
    by_id = {item.candidate_id: item for item in value.candidates}
    return PublicProductStrategy(
        programId=value.program_id, therapeuticObjective=value.therapeutic_objective,
        currentProvisionalLead=value.current_provisional_lead_candidate_id,
        recommendationStatus=value.latest_determination.determination.value,
        humanReviewStatus=value.latest_determination.approval_status.value,
        lastAssessedAt=value.updated_at,
        scoringExplanation="Potential contributions use fixed weights and 0-5 ratings; decision scores apply explicit confidence factors (missing 0, low 0.50, moderate 0.75, high 1.00). Hard gates remain separate.",
        disclaimer="Scores are not probabilities of success, efficacy, safety, approval, or clinical benefit. Candidate roles are provisional and human-gated.",
        dimensions=[PublicStrategyDimension(dimension=d, title=DIMENSION_TITLES[d][0],
            weight=value.dimension_weights[d], description=DIMENSION_TITLES[d][1]) for d in value.dimension_weights],
        candidateLeaderboard=ranking, candidates=[by_id[item] for item in ranking],
        scoreChangeHistory=value.assessment_history, currentCouncilReview=value.latest_determination,
    )
