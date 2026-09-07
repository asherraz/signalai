"""Derive the public Network + Intelligence product from canonical SignalAI state."""

from __future__ import annotations

from signalai.schemas.clinical_network import (
    ClinicalNetworkState,
    ReviewStatus,
)
from signalai.schemas.models import SignalState
from signalai.schemas.public import PublicChange
from signalai.schemas.public_artifacts import PublicLatestRun
from signalai.schemas.public_clinical_network import PublicClinicalNetwork
from signalai.schemas.public_product import (
    AccessTier,
    FoundingNetworkStatus,
    IntelligenceFeedType,
    IntelligenceImportance,
    IntelligenceModuleStatus,
    PublicAccessDefinition,
    PublicAccessModel,
    PublicAirbDetermination,
    PublicClinicIntelligenceView,
    PublicIntelligenceFeedItem,
    PublicIntelligenceIndex,
    PublicIntelligenceModule,
    PublicPartnerIntelligence,
    PublicProduct,
    PublicProductNetwork,
    PublicProductProgram,
    PublicProgramsIndex,
)
from signalai.schemas.workspace import TherapeuticAssetWorkspace


def _module(
    *,
    module_id: str,
    title: str,
    summary: str,
    last_updated,
    status: IntelligenceModuleStatus,
    preview: str,
    metrics: dict[str, int | str],
    changes: list[str],
    partner_summary: str,
    reference_ids: list[str],
    available_fields: list[str],
) -> PublicIntelligenceModule:
    return PublicIntelligenceModule(
        moduleId=module_id,
        title=title,
        summary=summary,
        lastUpdated=last_updated,
        status=status,
        publicPreview=preview,
        accessTier=AccessTier.PARTNER,
        keyMetrics=metrics,
        recentChanges=changes,
        partnerIntelligence=PublicPartnerIntelligence(
            summary=partner_summary,
            referenceIds=reference_ids,
            availableFields=available_fields,
            accessTier=AccessTier.PARTNER,
        ),
    )


def export_product_layer(
    scientific_state: SignalState,
    workspace: TherapeuticAssetWorkspace,
    clinical_state: ClinicalNetworkState,
    public_network: PublicClinicalNetwork,
    *,
    changes: list[PublicChange],
    latest_run: PublicLatestRun | None,
) -> tuple[PublicProduct, list[PublicIntelligenceFeedItem]]:
    """Build product navigation and feed without mutating or copying canonical state."""

    public_ids = {clinic.clinic_id for clinic in public_network.clinic_profiles}
    interested_ids = sorted(
        {
            interest.clinic_id
            for interest in clinical_state.partnership_interests
            if interest.clinic_id in public_ids
            and interest.status is ReviewStatus.APPROVED
            and scientific_state.program.program_id in interest.program_ids
        }
    )
    recent_network_ids = [
        clinic.clinic_id
        for clinic in sorted(
            (
                item
                for item in clinical_state.clinics
                if item.clinic_id in public_ids and item.approved_at is not None
            ),
            key=lambda item: item.approved_at,
            reverse=True,
        )[:5]
    ]
    network = PublicProductNetwork(
        approvedPublicClinicCount=public_network.summary.public_clinics,
        countriesRepresented=public_network.countries_represented,
        jurisdictionsRepresented=public_network.jurisdictions_represented,
        partnerStatusCounts=public_network.partner_status_counts,
        foundingNetworkStatus=(
            FoundingNetworkStatus.ACTIVE
            if public_network.summary.public_clinics
            else FoundingNetworkStatus.FORMING
        ),
        publicClinicCards=public_network.clinic_profiles,
        sgl001InterestedClinicIds=interested_ids,
        recentNetworkAdditionIds=recent_network_ids,
    )

    recent_scientific_changes = [item.summary for item in changes]
    latest_update = (
        latest_run.completed_at if latest_run is not None else scientific_state.generated_at
    )
    modules = [
        _module(
            module_id="therapeutic-programs",
            title="Therapeutic Programs",
            summary="Structured development state for SignalAI therapeutic assets.",
            last_updated=scientific_state.generated_at,
            status=IntelligenceModuleStatus.AWAITING_HUMAN_REVIEW,
            preview=(
                f"{scientific_state.program.asset_name} is in "
                f"{scientific_state.program.status.value} development with "
                f"{scientific_state.program.evidence_confidence.value} evidence confidence."
            ),
            metrics={"programs": 1, "openRisks": len(scientific_state.risks)},
            changes=recent_scientific_changes,
            partner_summary="Program hypothesis, risks, decisions, and next action are available for review.",
            reference_ids=[
                scientific_state.program.program_id,
                scientific_state.hypothesis.hypothesis_id,
                scientific_state.decision.decision_id,
            ],
            available_fields=["hypothesis", "risks", "decision", "nextAction"],
        ),
        _module(
            module_id="cargo",
            title="Cargo",
            summary="Biological cargo candidates and pathway-convergence intelligence.",
            last_updated=workspace.generated_at,
            status=IntelligenceModuleStatus.AVAILABLE,
            preview=f"{len(workspace.cargo.candidates)} cargo candidates are indexed.",
            metrics={
                "candidates": len(workspace.cargo.candidates),
                "pathways": len(workspace.cargo.pathways),
                "focusCandidates": len(workspace.cargo.operator_focus_candidate_ids),
            },
            changes=[],
            partner_summary="Candidate evidence, rationale, uncertainty, and pathway links are available.",
            reference_ids=workspace.cargo.operator_focus_candidate_ids,
            available_fields=["candidates", "pathways", "candidatePathwayLinks", "nextActions"],
        ),
        _module(
            module_id="formulation",
            title="Formulation",
            summary="Inspectable formulation, excipient, and presentation design space.",
            last_updated=workspace.generated_at,
            status=IntelligenceModuleStatus.AVAILABLE,
            preview=f"{len(workspace.formulation.candidates)} formulation candidates are indexed.",
            metrics={
                "candidates": len(workspace.formulation.candidates),
                "excipients": len(workspace.formulation.excipients),
                "presentations": len(workspace.formulation.presentations),
            },
            changes=[],
            partner_summary="Candidate tradeoffs, ordinal scores, excipients, and next actions are available.",
            reference_ids=[item.formulation_candidate_id for item in workspace.formulation.candidates],
            available_fields=["candidates", "excipients", "presentations", "nextActions"],
        ),
        _module(
            module_id="jurisdictions",
            title="Jurisdictions",
            summary="Provenance-linked jurisdiction and private-clinic pathway assessments.",
            last_updated=workspace.generated_at,
            status=IntelligenceModuleStatus.DEVELOPING,
            preview=f"{len(workspace.jurisdictions.jurisdictions)} jurisdictions are indexed.",
            metrics={
                "jurisdictions": len(workspace.jurisdictions.jurisdictions),
                "sourceDocuments": len(workspace.jurisdictions.sources),
            },
            changes=[],
            partner_summary="Verdicts, enforcement context, confidence, sources, and unresolved questions are available.",
            reference_ids=[
                item.jurisdiction_id for item in workspace.jurisdictions.jurisdictions
            ],
            available_fields=["verdict", "enforcement", "sources", "nextAction"],
        ),
        _module(
            module_id="evidence",
            title="Evidence",
            summary="Traceable evidence supporting or challenging current scientific claims.",
            last_updated=scientific_state.generated_at,
            status=IntelligenceModuleStatus.AVAILABLE,
            preview=f"{len(scientific_state.evidence)} curated evidence records support the current state.",
            metrics={
                "evidenceRecords": len(scientific_state.evidence),
                "claims": len(scientific_state.claims),
            },
            changes=[],
            partner_summary="Evidence provenance and claim relationships are available for audit.",
            reference_ids=[item.evidence_id for item in scientific_state.evidence],
            available_fields=["provenance", "claims", "supportingEvidence", "contradictions"],
        ),
        _module(
            module_id="airb",
            title="aiRB",
            summary="AI review-board critique and human-gated development determinations.",
            last_updated=latest_update,
            status=IntelligenceModuleStatus.AWAITING_HUMAN_REVIEW,
            preview=(
                f"The current determination is {scientific_state.decision.approval_status.value}."
            ),
            metrics={
                "decisions": 1,
                "approvalStatus": scientific_state.decision.approval_status.value,
            },
            changes=recent_scientific_changes,
            partner_summary="Critique, rationale, linked evidence, and approval state are available.",
            reference_ids=[scientific_state.decision.decision_id],
            available_fields=["critique", "determination", "rationale", "approvalStatus"],
        ),
    ]

    approved_program_matches = [
        item
        for item in public_network.program_matches
        if item.program_id == scientific_state.program.program_id
    ]
    program = PublicProductProgram(
        programId=scientific_state.program.program_id,
        name=scientific_state.program.asset_name,
        developmentFocus=scientific_state.program.development_focus,
        currentHypothesis=scientific_state.hypothesis.statement,
        evidenceConfidence=scientific_state.program.evidence_confidence,
        developmentStage=scientific_state.program.status,
        currentBlocker=scientific_state.program.largest_unresolved_risk,
        nextAction=scientific_state.program.next_proposed_action,
        currentAiRBDetermination=PublicAirbDetermination(
            decisionId=scientific_state.decision.decision_id,
            determination=scientific_state.decision.outcome,
            approvalStatus=scientific_state.decision.approval_status,
            humanApprovalRequired=scientific_state.decision.requires_human_approval,
        ),
        interestedClinicCount=len(interested_ids),
        approvedClinicPartnerCount=len(approved_program_matches),
    )
    clinic_view = PublicClinicIntelligenceView(
        personalizationStatus="not_personalized",
        relevantProgramIds=[scientific_state.program.program_id],
        recentChanges=recent_scientific_changes,
        relevantJurisdictionIds=[
            item.jurisdiction_id for item in workspace.jurisdictions.jurisdictions
        ],
        evidenceConfidenceByProgram={
            scientific_state.program.program_id: scientific_state.program.evidence_confidence
        },
        majorRisks=[item.title for item in scientific_state.risks],
        availableActions=[
            value
            for value in [
                scientific_state.program.next_proposed_action,
                "Express interest in evaluating a future SignalAI program.",
            ]
            if value
        ],
    )
    product = PublicProduct(
        network=network,
        intelligence=PublicIntelligenceIndex(modules=modules, clinicView=clinic_view),
        programs=PublicProgramsIndex(programs=[program]),
        access=PublicAccessModel(
            tiers=[
                PublicAccessDefinition(
                    tier=AccessTier.PUBLIC,
                    title="Public",
                    description="Concise program previews and approved public network profiles.",
                    currentlyEnforcedServerSide=False,
                ),
                PublicAccessDefinition(
                    tier=AccessTier.PARTNER,
                    title="Partner",
                    description="Deeper scientific, product, jurisdiction, and aiRB intelligence intended for partners.",
                    currentlyEnforcedServerSide=False,
                ),
                PublicAccessDefinition(
                    tier=AccessTier.PRO,
                    title="Pro",
                    description="Reserved for a future professional intelligence offering.",
                    currentlyEnforcedServerSide=False,
                ),
            ],
            billingEnabled=False,
            authenticationEnabled=False,
        ),
    )

    feed = [
        PublicIntelligenceFeedItem(
            itemId=f"feed-{item.change_id}",
            type=IntelligenceFeedType.PROGRAM_STATE_CHANGE,
            title="Program state reviewed",
            summary=item.summary,
            domain="program",
            programId=scientific_state.program.program_id,
            importance=IntelligenceImportance.MODERATE,
            accessTier=AccessTier.PUBLIC,
            createdAt=latest_update,
            linkedArtifactIds=[item.change_id],
        )
        for item in changes
    ]
    if latest_run is not None:
        feed.append(
            PublicIntelligenceFeedItem(
                itemId=f"feed-airb-{latest_run.run_id}",
                type=IntelligenceFeedType.AIRB_DETERMINATION,
                title="aiRB determination available",
                summary=(
                    latest_run.stages.decision.rationale
                    or "The latest human-gated aiRB determination is available for review."
                ),
                domain="airb",
                programId=scientific_state.program.program_id,
                importance=IntelligenceImportance.HIGH,
                accessTier=AccessTier.PARTNER,
                createdAt=latest_run.completed_at,
                linkedArtifactIds=[latest_run.run_id],
                linkedReviewIds=[latest_run.run_id],
                linkedDecisionIds=[latest_run.stages.decision.decision_id],
            )
        )
    return product, feed
