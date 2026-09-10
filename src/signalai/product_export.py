"""Derive the public Network + Intelligence product from canonical SignalAI state."""

from __future__ import annotations

from collections import Counter

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
    DataOrigin,
    FoundingNetworkStatus,
    IntelligenceFeedType,
    IntelligenceImportance,
    IntelligenceModuleStatus,
    PublicAccessDefinition,
    PublicAccessModel,
    PublicAirbDetermination,
    PublicClinicIntelligenceView,
    PublicContributionPolicy,
    PublicEcosystem,
    PublicEcosystemDomain,
    PublicIntelligenceCategory,
    PublicIntelligenceFeedItem,
    PublicIntelligenceIndex,
    PublicIntelligenceModule,
    PublicPartnerIntelligence,
    PublicProduct,
    PublicProductNetwork,
    PublicProductProgram,
    PublicProgramsIndex,
    PublicLearningLoop,
    PublicLearningLoopStage,
    PublicSignalNarrative,
    ProductLayerStatus,
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
        nicheDescription=(
            "Regenerative medicine clinics working with stem cells, exosomes and "
            "cell-derived therapies."
        ),
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
        networkThesis=public_network.network_thesis,
        clinicArchetypeCounts=dict(
            sorted(
                Counter(
                    clinic.regenerative_archetype.value
                    for clinic in public_network.clinic_profiles
                    if clinic.regenerative_archetype is not None
                ).items()
            )
        ),
        opportunitySummaries=public_network.opportunity_summaries,
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
        _module(
            module_id="exosome-product-review",
            title="Exosome Product Review",
            summary=(
                "Reusable product-diligence submodule for exosome and EV offerings "
                "inside the broader regenerative-clinic model."
            ),
            last_updated=clinical_state.generated_at,
            status=IntelligenceModuleStatus.DEVELOPING,
            preview="Exosome-specific diligence remains available as a focused submodule.",
            metrics={
                "productReviews": sum(
                    len(item.exosome_product_reviews)
                    for item in clinical_state.opportunity_assessments
                )
            },
            changes=[],
            partner_summary=(
                "Review product characterization, supplier provenance, supporting "
                "evidence, and jurisdiction-specific gaps."
            ),
            reference_ids=[
                review.review_id
                for item in clinical_state.opportunity_assessments
                for review in item.exosome_product_reviews
            ],
            available_fields=[
                "productCharacterization",
                "supplierProvenance",
                "evidenceGaps",
                "jurisdictionQuestions",
            ],
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
        programNumber="001",
        roleInSignal=(
            "The first therapeutic program developed through the Signal intelligence layer."
        ),
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
    intelligence_categories = [
        PublicIntelligenceCategory(
            categoryId="structured-evidence",
            title="Structured Evidence",
            summary="Evidence and claims linked through traceable provenance.",
            moduleIds=["evidence"],
            inputOrigins=[DataOrigin.PUBLIC_SOURCE, DataOrigin.OPERATOR_CURATED],
            status=ProductLayerStatus.ACTIVE,
        ),

        PublicIntelligenceCategory(
            categoryId="product-intelligence",
            title="Product Intelligence",
            summary="Cargo, formulation, product-specification, and focused EV diligence.",
            moduleIds=["cargo", "formulation", "exosome-product-review"],
            inputOrigins=[DataOrigin.OPERATOR_CURATED, DataOrigin.FUTURE_OPT_IN],
            status=ProductLayerStatus.ACTIVE,
        ),
        PublicIntelligenceCategory(
            categoryId="jurisdiction-intelligence",
            title="Jurisdiction Intelligence",
            summary="Source-linked regulatory and deployment context without equating enforcement with legality.",
            moduleIds=["jurisdictions"],
            inputOrigins=[DataOrigin.PUBLIC_SOURCE, DataOrigin.OPERATOR_CURATED],
            status=ProductLayerStatus.ACTIVE,
        ),
        PublicIntelligenceCategory(
            categoryId="clinic-intelligence",
            title="Clinic Intelligence",
            summary="Opt-in clinic portfolio, diligence, capability, and program-fit intelligence.",
            moduleIds=["therapeutic-programs", "exosome-product-review"],
            inputOrigins=[DataOrigin.PARTNER_CONTRIBUTED, DataOrigin.FUTURE_OPT_IN],
            status=(
                ProductLayerStatus.ACTIVE
                if public_network.summary.public_clinics
                else ProductLayerStatus.EMPTY
            ),
        ),
        PublicIntelligenceCategory(
            categoryId="airb-determinations",
            title="aiRB Determinations",
            summary="Critique and human-gated development determinations linked to evidence and risks.",
            moduleIds=["airb"],
            inputOrigins=[DataOrigin.PUBLIC_SOURCE, DataOrigin.OPERATOR_CURATED],
            status=ProductLayerStatus.ACTIVE,
        ),
    ]
    public_therapy_names = {
        therapy
        for clinic in public_network.clinic_profiles
        for therapy in (
            clinic.stem_cell_therapies_offered
            + clinic.exosome_ev_therapies_offered
            + clinic.secretome_cell_derived_products
        )
    }
    public_evidence_source_count = len(scientific_state.evidence)
    jurisdiction_source_count = len(workspace.jurisdictions.sources)
    ecosystem = PublicEcosystem(
        clinics=PublicEcosystemDomain(
            domainId="clinics",
            title="Clinics",
            summary="Approved regenerative-medicine clinics participating in the public network.",
            entityCount=public_network.summary.public_clinics,
            status=(
                ProductLayerStatus.ACTIVE
                if public_network.summary.public_clinics
                else ProductLayerStatus.EMPTY
            ),
            recordCountsByOrigin={
                DataOrigin.PARTNER_CONTRIBUTED: public_network.summary.public_clinics
            },
            partnerContributionOptInRequired=True,
        ),
        therapies=PublicEcosystemDomain(
            domainId="therapies",
            title="Therapies",
            summary="Opt-in clinic portfolios spanning stem cells, EVs, secretome, and cell-derived therapies.",
            entityCount=len(public_therapy_names),
            status=ProductLayerStatus.ACTIVE if public_therapy_names else ProductLayerStatus.EMPTY,
            recordCountsByOrigin={DataOrigin.PARTNER_CONTRIBUTED: len(public_therapy_names)},
            partnerContributionOptInRequired=True,
        ),
        products=PublicEcosystemDomain(
            domainId="products",
            title="Products and Specifications",
            summary="Structured formulation candidates and future opt-in partner product specifications.",
            entityCount=len(workspace.formulation.candidates),
            status=ProductLayerStatus.ACTIVE,
            recordCountsByOrigin={
                DataOrigin.OPERATOR_CURATED: len(workspace.formulation.candidates),
                DataOrigin.PARTNER_CONTRIBUTED: 0,
            },
            partnerContributionOptInRequired=True,
        ),
        jurisdictions=PublicEcosystemDomain(
            domainId="jurisdictions",
            title="Jurisdictions",
            summary="Structured jurisdiction assessments supported by retained source documents.",
            entityCount=len(workspace.jurisdictions.jurisdictions),
            status=ProductLayerStatus.ACTIVE,
            recordCountsByOrigin={
                DataOrigin.PUBLIC_SOURCE: jurisdiction_source_count,
                DataOrigin.OPERATOR_CURATED: len(workspace.jurisdictions.jurisdictions),
            },
            partnerContributionOptInRequired=True,
        ),
        evidenceSources=PublicEcosystemDomain(
            domainId="evidence-sources",
            title="Evidence Sources",
            summary="Scientific and jurisdiction sources retained with provenance.",
            entityCount=public_evidence_source_count + jurisdiction_source_count,
            status=ProductLayerStatus.ACTIVE,
            recordCountsByOrigin={
                DataOrigin.PUBLIC_SOURCE: public_evidence_source_count
                + jurisdiction_source_count
            },
            partnerContributionOptInRequired=True,
        ),
    )
    learning_loop = PublicLearningLoop(
        summary=(
            "Signal structures evidence, product, clinic, and jurisdiction inputs into "
            "analysis that advances programs and returns useful intelligence to the network."
        ),
        stages=[
            PublicLearningLoopStage(
                sequence=1,
                stageId="public-evidence",
                title="Public Evidence",
                summary="Curated scientific and regulatory sources enter with provenance.",
                status=ProductLayerStatus.ACTIVE,
                dataOrigins=[DataOrigin.PUBLIC_SOURCE],
                currentRecordCount=public_evidence_source_count + jurisdiction_source_count,
                optInRequired=False,
            ),
            PublicLearningLoopStage(
                sequence=2,
                stageId="clinic-protocols",
                title="Clinic Protocols",
                summary="Future partner-contributed protocols require explicit clinic opt-in.",
                status=ProductLayerStatus.FUTURE,
                dataOrigins=[DataOrigin.FUTURE_OPT_IN, DataOrigin.PARTNER_CONTRIBUTED],
                currentRecordCount=0,
                optInRequired=True,
            ),
            PublicLearningLoopStage(
                sequence=3,
                stageId="product-specifications",
                title="Product Specifications",
                summary="Structured formulation state can be joined with future opt-in partner specifications.",
                status=ProductLayerStatus.ACTIVE,
                dataOrigins=[DataOrigin.OPERATOR_CURATED, DataOrigin.FUTURE_OPT_IN],
                currentRecordCount=len(workspace.formulation.candidates),
                optInRequired=True,
            ),
            PublicLearningLoopStage(
                sequence=4,
                stageId="deidentified-outcomes",
                title="Future De-identified Outcomes",
                summary="No outcomes are collected; any future contribution must be opt-in and de-identified.",
                status=ProductLayerStatus.FUTURE,
                dataOrigins=[DataOrigin.FUTURE_OPT_IN],
                currentRecordCount=0,
                optInRequired=True,
            ),
            PublicLearningLoopStage(
                sequence=5,
                stageId="structured-analysis",
                title="Structured Analysis",
                summary="SignalAI links evidence, hypotheses, critique, risks, and decisions.",
                status=ProductLayerStatus.ACTIVE,
                dataOrigins=[DataOrigin.PUBLIC_SOURCE, DataOrigin.OPERATOR_CURATED],
                currentRecordCount=len(scientific_state.claims),
                optInRequired=False,
            ),
            PublicLearningLoopStage(
                sequence=6,
                stageId="program-development",
                title="Program Development",
                summary="Structured intelligence guides human-gated therapeutic development programs.",
                status=ProductLayerStatus.ACTIVE,
                dataOrigins=[DataOrigin.OPERATOR_CURATED],
                currentRecordCount=1,
                optInRequired=False,
            ),
            PublicLearningLoopStage(
                sequence=7,
                stageId="network-intelligence-return",
                title="Return Intelligence to the Network",
                summary="Public previews and partner intelligence return structured learning to participants.",
                status=ProductLayerStatus.READY,
                dataOrigins=[DataOrigin.OPERATOR_CURATED],
                currentRecordCount=len(changes) + (1 if latest_run is not None else 0),
                optInRequired=False,
            ),
        ],
    )
    product = PublicProduct(
        network=network,
        intelligence=PublicIntelligenceIndex(
            modules=modules,
            clinicView=clinic_view,
            categories=intelligence_categories,
        ),
        programs=PublicProgramsIndex(
            programs=[program],
            summary=(
                "SGL-001 is Program 001 and the first therapeutic program developed "
                "through the Signal intelligence layer; the index supports future programs."
            ),
            supportsFuturePrograms=True,
        ),
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
                    description=(
                        "Deeper scientific, product, jurisdiction, and aiRB intelligence "
                        "for regenerative medicine clinics working with stem cells, "
                        "exosomes and cell-derived therapies."
                    ),
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
        thesis=PublicSignalNarrative(
            companyThesis="Signal is the intelligence layer for regenerative medicine.",
            whatSignalIs=(
                "Signal connects and structures the global regenerative-medicine "
                "ecosystem across clinics, therapies, products, evidence, and jurisdictions."
            ),
            fragmentedProblem=(
                "Regenerative-medicine evidence, product specifications, clinic protocols, "
                "jurisdiction context, and outcomes are fragmented and difficult to compare."
            ),
            howAiCreatesValue=(
                "SignalAI converts traceable inputs into structured claims, product and "
                "jurisdiction intelligence, critiques, risks, and human-gated decisions."
            ),
            networkContribution=(
                "Clinics may opt in to contribute portfolio, protocol, product, and future "
                "de-identified outcomes data while retaining explicit provenance and controls."
            ),
            programEmergence=(
                "Cross-ecosystem intelligence reveals evidence gaps and development "
                "opportunities from which new human-approved therapeutic programs can emerge."
            ),
            sgl001ProofPoint=(
                "SGL-001 is Program 001: the first therapeutic program developed through "
                "the Signal intelligence layer, not the full scope of the company."
            ),
        ),
        ecosystem=ecosystem,
        learningLoop=learning_loop,
        contributionPolicy=PublicContributionPolicy(
            partnerContributionOptInRequired=True,
            defaultPartnerDataVisibility="private_until_explicitly_approved_for_publication",
            publicSourceProvenanceRequired=True,
            partnerProvenanceRequired=True,
            outcomeDataStatus=ProductLayerStatus.FUTURE,
            outcomePrivacyStandard=(
                "Future outcomes must be de-identified and governed before collection or use."
            ),
            contributionTypes=[
                "clinic_protocols",
                "product_specifications",
                "portfolio_information",
                "future_deidentified_outcomes",
            ],
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
