"""Strict public JSON contract consumed by the separate frontend."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AliasChoices, Field, model_validator
from signalai.schemas.signalrb import PublicSignalRB, SignalReviewBoardDetermination
from signalai.schemas.public_flagship import PublicFlagshipProgram
from signalai.schemas.public_manufacturing import PublicManufacturingState

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
from signalai.schemas.public_artifacts import (
    PublicAiRBState,
    PublicHypothesisArtifact,
    PublicLatestRun,
)
from signalai.schemas.public_clinical_network import PublicClinicalNetwork
from signalai.schemas.public_clinic_intelligence import PublicClinicIntelligence
from signalai.schemas.public_live import PublicLiveIntelligence
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
    airb: PublicAiRBState | None = Field(default=None, alias="aiRB", validation_alias=AliasChoices("aiRB", "airb", "aiRB determination"))
    signal_rb: PublicSignalRB | None = Field(default=None, alias="signalRB")
    flagship_program: PublicFlagshipProgram | None = Field(default=None, alias="flagshipProgram")
    cargo: PublicCargoState | None = None
    formulation: PublicFormulationState | None = None
    manufacturing: PublicManufacturingState | None = None
    jurisdictions: PublicJurisdictionState | None = None
    clinical_network: PublicClinicalNetwork | None = Field(
        default=None,
        alias="clinicalNetwork",
    )
    clinic_intelligence: PublicClinicIntelligence | None = Field(default=None, alias="clinicIntelligence")
    product: PublicProduct | None = None
    intelligence_feed: list[PublicIntelligenceFeedItem] = Field(
        default_factory=list,
        alias="intelligenceFeed",
    )
    live_intelligence: PublicLiveIntelligence | None = Field(
        default=None, alias="liveIntelligence"
    )

    @model_validator(mode="after")
    def migrate_legacy_board(self):
        if self.signal_rb is None and self.airb is not None:
            old = self.airb
            decision = old.determination
            pending = decision.human_approval_required and decision.approval_status.value == "pending"
            review = SignalReviewBoardDetermination(
                review_id=old.review_id, run_id=old.run_id, program_id=old.program_id,
                matter_id=self.latest_run.selected_task.agenda_item_id if self.latest_run and self.latest_run.run_id == old.run_id else "not_recorded",
                matter_title=decision.question, matter_question=decision.question,
                domain="not_recorded", reviewers=["not_recorded"],
                strongest_case_for=decision.rationale or "not_recorded",
                strongest_case_against=old.critique.strongest_objection,
                verification_status="not_recorded", determination=decision.recommendation or "not_recorded",
                determination_type="human_decision_required" if pending else "not_recorded",
                conditions=old.critique.falsification_conditions,
                evidence_ids=list(dict.fromkeys(decision.linked_evidence_ids + old.critique.disconfirming_evidence_ids)),
                state_change="not_recorded", human_decision_required=pending,
                next_action=self.latest_run.stages.next_action.action if self.latest_run and self.latest_run.run_id == old.run_id else "not_recorded",
                created_at=old.last_updated,
            )
            object.__setattr__(self, "signal_rb", PublicSignalRB(latestReview=review, recentReviews=[review], summary={"reviews": 1}))
        return self

    @model_validator(mode="after")
    def validate_public_state(self) -> PublicSignalState:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        if self.program.program_id != "SGL-001":
            raise ValueError("Milestone 1 public state must describe SGL-001")
        if self.signal_rb:
            allowed = {e.evidence_id for e in self.evidence}
            reviews = self.signal_rb.recent_reviews + ([self.signal_rb.latest_review] if self.signal_rb.latest_review else [])
            if any(set(r.evidence_ids) - allowed for r in reviews) or any(set(d.evidence_ids) - allowed for d in self.signal_rb.pending_human_decisions):
                raise ValueError("SignalRB references unknown canonical evidence")
        if self.flagship_program:
            flagship = self.flagship_program
            if flagship.program_id != self.program.program_id:
                raise ValueError("flagship program must match canonical program")
            allowed = {
                "claim_ids": {c.claim_id for c in self.program.claims},
                "evidence_ids": {e.evidence_id for e in self.evidence},
                "risk_ids": {r.risk_id for r in self.risks},
                "hypothesis_ids": {h.hypothesis_id for h in self.hypotheses},
                "review_ids": {r.review_id for r in self.signal_rb.recent_reviews} if self.signal_rb else set(),
                "program_fields": set(TherapeuticProgram.model_fields),
            }
            if self.signal_rb and self.signal_rb.latest_review:
                allowed["review_ids"].add(self.signal_rb.latest_review.review_id)
            refs = [flagship.sources, flagship.thesis.sources] + [g.sources for g in flagship.development_gates]
            if any(set(getattr(ref, field)) - ids for ref in refs for field, ids in allowed.items()):
                raise ValueError("flagship sources must reference canonical state")
            reviews = {r.review_id: r for r in self.signal_rb.recent_reviews} if self.signal_rb else {}
            if self.signal_rb and self.signal_rb.latest_review:
                reviews[self.signal_rb.latest_review.review_id] = self.signal_rb.latest_review
            if flagship.signal_rb_review_id and flagship.signal_rb_review_id not in reviews:
                raise ValueError("flagship links an unknown SignalRB review")
            for pivot in flagship.pivot_criteria:
                review = reviews.get(pivot.review_id)
                if not review or pivot.condition not in review.conditions or set(pivot.evidence_ids) - set(review.evidence_ids):
                    raise ValueError("pivot criterion must come from a recorded SignalRB condition")
            if any(h.review_id not in reviews or h.run_id != reviews[h.review_id].run_id for h in flagship.program_history):
                raise ValueError("flagship history must link canonical reviews and runs")
            if flagship.manufacturing and self.manufacturing:
                if flagship.manufacturing.latest_relevant_determination_id != self.manufacturing.latest_relevant_determination_id:
                    raise ValueError("flagship manufacturing must reference the canonical manufacturing determination")
        if self.manufacturing:
            if self.manufacturing.program_id != self.program.program_id:
                raise ValueError("public manufacturing must match the canonical program")
            refs = [self.manufacturing.product_definition.refs, self.manufacturing.potency.refs]
            refs.extend(item.refs for group in (
                self.manufacturing.process_stages, self.manufacturing.quality_attributes,
                self.manufacturing.readiness, self.manufacturing.risks,
                self.manufacturing.next_actions,
            ) for item in group)
            allowed_evidence = {item.evidence_id for item in self.evidence}
            allowed_claims = {item.claim_id for item in self.program.claims}
            allowed_risks = {item.risk_id for item in self.risks}
            allowed_decisions = {item.decision_id for item in self.decisions}
            if any(set(ref.evidence_ids) - allowed_evidence for ref in refs):
                raise ValueError("public manufacturing references unknown evidence")
            if any(set(ref.claim_ids) - allowed_claims for ref in refs):
                raise ValueError("public manufacturing references unknown claims")
            if any(set(ref.risk_ids) - allowed_risks for ref in refs):
                raise ValueError("public manufacturing references unknown risks")
            if any(set(ref.decision_ids) - allowed_decisions for ref in refs):
                raise ValueError("public manufacturing references unknown decisions")
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
        airb: PublicAiRBState | None = None,
        cargo: PublicCargoState | None = None,
        formulation: PublicFormulationState | None = None,
        manufacturing: PublicManufacturingState | None = None,
        jurisdictions: PublicJurisdictionState | None = None,
        clinical_network: PublicClinicalNetwork | None = None,
        clinic_intelligence: PublicClinicIntelligence | None = None,
        product: PublicProduct | None = None,
        intelligence_feed: list[PublicIntelligenceFeedItem] | None = None,
        live_intelligence: PublicLiveIntelligence | None = None,
        generated_at: datetime | None = None,
    ) -> PublicSignalState:
        public = cls(
            generatedAt=generated_at or state.generated_at,
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
            aiRB=airb,
            cargo=cargo,
            formulation=formulation,
            manufacturing=manufacturing,
            jurisdictions=jurisdictions,
            clinicalNetwork=clinical_network,
            clinicIntelligence=clinic_intelligence,
            product=product,
            intelligenceFeed=intelligence_feed or [],
            liveIntelligence=live_intelligence,
        )
        from signalai.flagship_export import export_flagship_program

        return public.model_copy(update={"flagship_program": export_flagship_program(state, public.signal_rb)})
