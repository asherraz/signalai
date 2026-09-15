"""Derive SignalRB from validated immutable artifacts, never model intuition."""

import json
from pathlib import Path

from signalai.schemas.live import LiveAdversaryReview, LiveAnalysis, LiveVerification, LiveRunHistory, LiveChairRecommendation
from signalai.schemas.models import ApprovalStatus, SignalState
from signalai.schemas.signalrb import PublicPendingBoardDecision, PublicSignalRB, SignalReviewBoardDetermination


def export_signalrb(root: Path, state: SignalState, history: LiveRunHistory | None) -> PublicSignalRB:
    reviews = {}
    allowed = {e.evidence_id for e in state.evidence}
    for run in history.runs if history else []:
        directory = root / "runs" / run.run_id
        analysis = LiveAnalysis.model_validate_json((directory / "05-analysis.json").read_text())
        verifier = LiveVerification.model_validate_json((directory / "06-verification.json").read_text())
        adversary = LiveAdversaryReview.model_validate_json((directory / "07-adversary.json").read_text())
        chair_data = json.loads((directory / "08-chair-determination.json").read_text())
        chair = None
        if isinstance(chair_data.get("recommendation"), dict):
            chair = LiveChairRecommendation.model_validate(chair_data["recommendation"])
            if chair.matter_id != run.selected_matter.matter_id:
                raise ValueError("SignalRB chair belongs to another matter")
        if any(item.matter_id != run.selected_matter.matter_id for item in (analysis, verifier, adversary)):
            raise ValueError("SignalRB supporting artifacts refer to another matter")
        evidence = list(dict.fromkeys(run.strongest_supporting_evidence_ids + run.strongest_contradictory_evidence_ids + verifier.verified_evidence_ids + adversary.disconfirming_evidence_ids))
        if chair:
            evidence = list(dict.fromkeys(evidence + chair.supporting_evidence_ids))
        if set(evidence) - allowed:
            raise ValueError("SignalRB references unknown canonical evidence")
        kind = "no_material_change"
        if run.chair_determination == "human_decision_required":
            kind = "human_decision_required"
        elif run.chair_determination in {"state_update", "decision_update"}:
            kind = "state_updated"
        review = SignalReviewBoardDetermination(
            review_id=f"signalrb-{run.run_id}", run_id=run.run_id, program_id=run.program_id,
            matter_id=run.selected_matter.matter_id, matter_title=run.selected_matter.title,
            matter_question=run.selected_matter.question, domain=run.selected_matter.domain.value,
            reviewers=[r.value for r in run.reviewers_convened],
            strongest_case_for=analysis.strongest_support_summary,
            strongest_case_against=adversary.strongest_objection,
            verification_status="unsupported_assertions" if verifier.unsupported_assertions else "verified",
            determination=chair.recommendation if chair else run.what_changed, determination_type=kind,
            conditions=adversary.falsification_conditions, evidence_ids=evidence,
            state_change=run.scientific_state_changed,
            human_decision_required=kind == "human_decision_required", next_action=run.next_action,
            created_at=run.completed_at,
        )
        reviews[run.run_id] = review
    ordered = sorted(reviews.values(), key=lambda r: (r.created_at, r.run_id), reverse=True)
    pending = [PublicPendingBoardDecision(
        decision_id=d.decision_id, program_id=d.program_id, question=d.question,
        outcome=d.outcome, approval_status=d.approval_status.value, evidence_ids=d.evidence_ids,
    ) for d in [state.decision] if d.requires_human_approval and d.approval_status == ApprovalStatus.PENDING]
    return PublicSignalRB(latestReview=ordered[0] if ordered else None, recentReviews=ordered,
                          pendingHumanDecisions=pending,
                          summary={"reviews": len(ordered), "pendingHumanDecisions": len(pending)})
