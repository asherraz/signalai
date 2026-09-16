"""Deterministic Manufacturing/CMC initialization and guarded updates."""

from __future__ import annotations

from signalai.schemas.agenda import DevelopmentAgenda
from signalai.schemas.live import DevelopmentDocket, LiveRunHistory
from signalai.schemas.manufacturing import (
    ManufacturingApprovalState, ManufacturingNextAction, ManufacturingRefs,
    ManufacturingRisk, ManufacturingState, ManufacturingStateLevel,
    PotencyStrategy, ProcessStage, ProductDefinition, QualityAttribute,
    ReadinessItem, Specification, TestMethod,
)
from signalai.schemas.models import SignalState
from signalai.schemas.workspace import TherapeuticAssetWorkspace


CMC_EVIDENCE = "ev-misev2023-quality-framework"
CMC_CLAIM = "claim-ev-cmc-requirements"
CMC_RISK = "risk-cmc-identity-potency"
CMC_MATTER = "matter-potency-identity-characterization"
PRODUCT_MATTER = "matter-candidate-product-definition"
FORMULATION_AGENDA = "agenda-formulation-source-cell"


def _refs(*, runs=(), matters=(), claims=(CMC_CLAIM,), risks=(), agenda=(), evidence=(CMC_EVIDENCE,)):
    return ManufacturingRefs(evidence_ids=list(evidence), claim_ids=list(claims),
        risk_ids=list(risks), agenda_item_ids=list(agenda), matter_ids=list(matters), run_ids=list(runs))


def build_initial_manufacturing(
    workspace: TherapeuticAssetWorkspace,
    state: SignalState,
    agenda: DevelopmentAgenda,
    docket: DevelopmentDocket,
    history: LiveRunHistory,
) -> ManufacturingState:
    """Map only accepted canonical facts and accepted determination metadata."""
    evidence_ids = {item.evidence_id for item in state.evidence}
    claim_ids = {item.claim_id for item in state.claims}
    risk = next((item for item in state.risks if item.risk_id == CMC_RISK), None)
    if CMC_EVIDENCE not in evidence_ids or CMC_CLAIM not in claim_ids or risk is None:
        raise ValueError("canonical CMC evidence, claim, and risk are required")
    matters = {item.matter_id for item in docket.matters}
    agenda_ids = {item.agenda_item_id for item in agenda.items}
    if {CMC_MATTER, PRODUCT_MATTER} - matters or FORMULATION_AGENDA not in agenda_ids:
        raise ValueError("canonical CMC docket and agenda references are required")
    relevant = [run for run in history.runs if run.selected_matter.matter_id == CMC_MATTER]
    latest = max(relevant, key=lambda item: item.completed_at or item.started_at) if relevant else None
    latest_run = latest.run_id if latest else None
    product_reviews = [run for run in history.runs if run.selected_matter.matter_id == PRODUCT_MATTER]
    product_run = max(product_reviews, key=lambda item: item.completed_at or item.started_at).run_id if product_reviews else None
    gap_refs = _refs(runs=[latest_run] if latest_run else [], matters=[CMC_MATTER], risks=[CMC_RISK], agenda=[FORMULATION_AGENDA])

    stages = []
    stage_definitions = [
        ("source-qualification", "Source qualification", "Source-cell qualification criteria and records are not defined."),
        ("cell-bank-strategy", "Cell-bank strategy", "MCB/WCB strategy and records are not defined."),
        ("msc-expansion", "MSC expansion", "Expansion platform and controls are not defined."),
        ("conditioning", "Conditioning", "Conditioning inputs and controls are not defined."),
        ("harvest", "Harvest", "Harvest timing and controls are not defined."),
        ("clarification", "Clarification", "Clarification approach and controls are not defined."),
        ("concentration-fraction-handling", "Concentration and fraction handling", "Purification and fraction-handling strategy is unresolved."),
        ("formulation", "Formulation", "Intranasal formulation is proposed; vehicle and stabilizer are unresolved."),
        ("fill-finish", "Fill/finish", "Fill/finish presentation and controls are not defined."),
        ("storage", "Storage", "Storage conditions and shelf life are not established."),
    ]
    for sequence, (key, name, missing) in enumerate(stage_definitions, 1):
        stages.append(ProcessStage(process_stage_id=f"process-{key}", name=name, sequence=sequence,
            state=ManufacturingStateLevel.PROPOSED if key == "formulation" else ManufacturingStateLevel.NOT_DEFINED,
            current_definition="Intranasal route is the current program route; product configuration remains proposed." if key == "formulation" else None,
            missing_information=[missing], refs=gap_refs))

    quality_requirements = {
        "particle-characterization": ("Particle characterization", "Orthogonal particle characterization is required."),
        "protein-lipid-markers": ("Protein and lipid marker characterization", "Protein and lipid marker characterization is required."),
        "non-vesicular-coisolates": ("Non-vesicular co-isolate assessment", "Non-vesicular co-isolates must be assessed."),
        "intact-ev-assay": ("Intact-EV assay", "Fit-for-purpose intact-EV identity testing requires sensitivity, specificity, and precision assessment."),
        "stability-indicating": ("Stability-indicating testing", "Stability-indicating testing is required; no SGL-001 stability result is recorded."),
        "mechanism-potency": ("Mechanism-linked potency", "A mechanism-linked potency strategy is required."),
    }
    methods = [TestMethod(method_id=f"method-proposal-{key}", name=name, purpose=purpose,
        state=ManufacturingStateLevel.PROPOSED, validation_status=ManufacturingStateLevel.NOT_DEFINED,
        refs=gap_refs) for key, (name, purpose) in quality_requirements.items()]
    formulation_attribute = next(item for item in workspace.formulation.attributes if item.attribute_id == "attribute-ev-identity-purity")
    quality = [QualityAttribute(quality_attribute_id=formulation_attribute.attribute_id,
        name=formulation_attribute.name, target=formulation_attribute.target,
        state=ManufacturingStateLevel.PROPOSED,
        proposed_requirements=[value[1] for value in quality_requirements.values()],
        numeric_acceptance_limits_defined=False,
        refs=_refs(risks=[CMC_RISK], agenda=[FORMULATION_AGENDA]))]

    readiness_states = {
        "product-definition": ManufacturingStateLevel.PROPOSED,
        "source-material-control": ManufacturingStateLevel.EVIDENCE_GAP,
        "cell-bank-strategy": ManufacturingStateLevel.EVIDENCE_GAP,
        "process-definition": ManufacturingStateLevel.NOT_DEFINED,
        "analytical-characterization": ManufacturingStateLevel.PROPOSED,
        "potency-assay": ManufacturingStateLevel.EVIDENCE_GAP,
        "release-specifications": ManufacturingStateLevel.PROPOSED,
        "sterility-assurance": ManufacturingStateLevel.NOT_ASSESSED,
        "stability-program": ManufacturingStateLevel.EVIDENCE_GAP,
        "lot-reproducibility": ManufacturingStateLevel.EVIDENCE_GAP,
        "scale-up": ManufacturingStateLevel.EVIDENCE_GAP,
        "fill-finish": ManufacturingStateLevel.NOT_DEFINED,
    }
    readiness = [ReadinessItem(readiness_id=f"readiness-{key}", dimension=key.replace("-", " ").title(),
        state=value, rationale=("A requirement or proposal is recorded, but program-specific verification is absent."
            if value in {ManufacturingStateLevel.PROPOSED, ManufacturingStateLevel.EVIDENCE_GAP}
            else "No canonical assessment or definition is recorded."), refs=gap_refs)
        for key, value in readiness_states.items()]

    action_texts = [
        ("source-cell-bank", "Define source-cell qualification and MCB/WCB strategy."),
        ("orthogonal-qc", "Establish an orthogonal QC panel."),
        ("draft-release-specifications", "Draft release specifications without asserting acceptance limits."),
        ("potency-stability-assays", "Develop fit-for-purpose potency and stability-indicating assays."),
        ("representative-scale-up", "Produce representative GMP-like scale-up batches; none are recorded yet."),
        ("release-stability-comparability", "Assess release, stability, and comparability after real batches exist."),
        ("formulation-device-compatibility", "Test formulation and device compatibility with intact-EV recovery controls."),
    ]
    actions = [ManufacturingNextAction(action_id=f"manufacturing-action-{key}", action=text,
        status=ManufacturingApprovalState.PROPOSED, requires_human_approval=True, refs=gap_refs)
        for key, text in action_texts]
    return ManufacturingState(
        program_id=state.program.program_id,
        product_definition=ProductDefinition(
            product_definition_id="product-definition-sgl001", program_id=state.program.program_id,
            route=state.program.route_of_administration,
            biological_concept="MSC-derived secretome/EV concept for an intranasal cell-free regenerative product.",
            ev_fraction_role="The EV/exosome fraction is intended to contribute biological signal, but its exact role and active contribution are unresolved.",
            drug_substance_identity=None, purification_fractionation_state=None,
            dose_definition=None, vehicle_stabilizer=None, state=ManufacturingStateLevel.PROPOSED,
            unresolved_decisions=["Secretome retaining EVs versus a small-EV preparation.",
                "Exact drug-substance identity and purification/fractionation state.",
                "Dose definition.", "Vehicle and stabilizer selection."],
            refs=_refs(runs=[product_run] if product_run else [], matters=[PRODUCT_MATTER], risks=[CMC_RISK], agenda=[FORMULATION_AGENDA])),
        process_stages=stages, quality_attributes=quality,
        potency_strategy=PotencyStrategy(potency_strategy_id="potency-strategy-sgl001",
            state=ManufacturingStateLevel.EVIDENCE_GAP,
            strategy="Develop a stability-indicating, mechanism-linked potency assay within an orthogonal QC framework.",
            particle_count_is_established_potency=False, validated_acceptance_criteria=False,
            gaps=["Potency framework is not established.", "No validated acceptance criteria are recorded.",
                "No program-specific potency result is recorded."], latest_determination_run_id=latest_run,
            latest_determination_id=f"signalrb-{latest_run}" if latest_run else None,
            prior_state_preserved=(not latest.state_changed) if latest else None, refs=gap_refs),
        test_methods=methods,
        specifications=[Specification(specification_id="specification-draft-release-sgl001",
            name="Draft SGL-001 release specification framework", version="proposal-1",
            approval_state=ManufacturingApprovalState.PROPOSED,
            method_ids=[item.method_id for item in methods], acceptance_criteria=[], refs=gap_refs)],
        test_results=[], lots=[], stability_programs=[], coa_records=[], readiness=readiness,
        risks=[ManufacturingRisk(risk_id=risk.risk_id, title=risk.title,
            description=risk.description, mitigation=risk.mitigation, owner=risk.owner,
            state=ManufacturingStateLevel.EVIDENCE_GAP, refs=gap_refs)],
        next_actions=actions, updated_at=latest.completed_at if latest and latest.completed_at else state.generated_at,
    )


def initialize_manufacturing(
    workspace: TherapeuticAssetWorkspace,
    state: SignalState,
    agenda: DevelopmentAgenda,
    docket: DevelopmentDocket,
    history: LiveRunHistory,
) -> TherapeuticAssetWorkspace:
    """Idempotently populate Manufacturing when loading a legacy workspace."""
    if workspace.manufacturing is not None:
        return workspace
    return workspace.model_copy(update={
        "schema_version": "1.1",
        "manufacturing": build_initial_manufacturing(workspace, state, agenda, docket, history),
    })


def apply_validated_manufacturing_update(
    workspace: TherapeuticAssetWorkspace,
    proposed: ManufacturingState,
    *,
    verification_supports_state_change: bool,
    human_approved: bool,
    state: SignalState,
    agenda: DevelopmentAgenda,
    docket: DevelopmentDocket,
    history: LiveRunHistory,
) -> TherapeuticAssetWorkspace:
    """Reject unsupported or unapproved CMC mutations without changing prior state."""
    if not verification_supports_state_change or not human_approved:
        return workspace
    if proposed.program_id != workspace.program_id:
        raise ValueError("manufacturing update belongs to another program")
    candidate = workspace.model_copy(update={"manufacturing": proposed})
    from signalai.workspace_export import validate_workspace_references
    validate_workspace_references(candidate, state, agenda)
    validate_manufacturing_operational_refs(proposed, docket, history)
    return candidate


def validate_manufacturing_operational_refs(
    manufacturing: ManufacturingState,
    docket: DevelopmentDocket,
    history: LiveRunHistory,
) -> None:
    matter_ids = {item.matter_id for item in docket.matters}
    run_ids = {item.run_id for item in history.runs}
    refs = [manufacturing.product_definition.refs, manufacturing.potency_strategy.refs]
    refs.extend(item.refs for group in (manufacturing.process_stages, manufacturing.quality_attributes,
        manufacturing.test_methods, manufacturing.specifications, manufacturing.test_results, manufacturing.lots,
        manufacturing.stability_programs, manufacturing.readiness, manufacturing.risks, manufacturing.next_actions)
        for item in group)
    if any(set(ref.matter_ids) - matter_ids for ref in refs):
        raise ValueError("manufacturing update references unknown docket matters")
    if any(set(ref.run_ids) - run_ids for ref in refs):
        raise ValueError("manufacturing update references unknown runs")
