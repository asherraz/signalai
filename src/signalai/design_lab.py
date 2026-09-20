"""Bounded, review-gated SGL-001 Product Design Lab."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from signalai.agents.design_lab_prompts import (
    CMC_REVIEWER, DESIGN_ADVERSARY, DESIGN_CHAIR, DESIGN_REPAIR,
    DESIGN_SCIENTIST, EVIDENCE_VERIFIER, MECHANISM_REVIEWER,
)
from signalai.client import ModelClient, StructuredOutputError
from signalai.design_lab_export import export_design_lab
from signalai.publisher import build_current_public_state
from signalai.schemas import SignalState, TherapeuticAssetWorkspace
from signalai.schemas.design_lab import (
    DesignAdversaryReview, DesignChairClassification, DesignDetermination,
    DesignGap, DesignHypothesis, DesignLabWorkspace, DesignProposal, DesignReview,
    DesignRunSummary, ReviewerFinding,
)
from signalai.schemas.live import DevelopmentDocket, LiveRunHistory
from signalai.storage import RunStore, new_run_id, publish_json


T = TypeVar("T", bound=BaseModel)


def _json(value: Any) -> str:
    return json.dumps(TypeAdapter(Any).dump_python(value, mode="json"), sort_keys=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, model: type[T]) -> T:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def initial_design_lab(now: datetime) -> DesignLabWorkspace:
    common = dict(testability=4, product_definition_relevance=5, manufacturing_relevance=5,
                  evidence_availability=2, discriminating_value=5)
    gaps = [
        DesignGap(gap_id="design-gap-product-identity", title="Product identity",
            question="Which orthogonal measurable attributes could define SGL-001 product identity without implying potency or efficacy?",
            domain="product_identity", blocking_value=5,
            rationale="Canonical Manufacturing records exact drug-substance identity and fractionation as unresolved.",
            priority=5, mechanistic_relevance=4, open_questions=["What defines the product independently of an efficacy claim?"], **common),
        DesignGap(gap_id="design-gap-source-cell", title="Source-cell definition",
            question="Which source-cell attributes should be evaluated for their relationship to a reproducible SGL-001 product signature?",
            domain="cell_source", blocking_value=5,
            rationale="Canonical Manufacturing records source qualification and cell-bank strategy as evidence gaps.",
            priority=5, mechanistic_relevance=4, open_questions=["Which source attributes merit comparative characterization?"], **common),
        DesignGap(gap_id="design-gap-surface-phenotype", title="Surface-marker phenotype",
            question="Which evidence-linked surface-phenotype measurements could help characterize product identity without implying potency?",
            domain="product_identity", blocking_value=4, priority=4, mechanistic_relevance=4,
            rationale="Surface phenotype is a possible characterization domain, not an established SGL-001 potency marker.",
            open_questions=["Which measurements are source- and process-sensitive?"], **common),
        DesignGap(gap_id="design-gap-cargo-composition", title="Cargo composition",
            question="Which evidence-linked cargo-profile comparison could test consistency without presuming an active molecule?",
            domain="cargo", blocking_value=4, priority=4, mechanistic_relevance=5,
            rationale="Cargo strategy and active biological contributors remain unresolved.",
            open_questions=["Does any cargo profile track a functional readout across future preparations?"], **common),
        DesignGap(gap_id="design-gap-ev-non-ev-composition", title="EV versus non-EV composition",
            question="Which fraction comparison could distinguish EV-associated from non-EV biological contributions?",
            domain="fractionation", blocking_value=5, priority=5, mechanistic_relevance=5,
            rationale="The relative contribution of EV and non-EV secretome components remains unresolved.",
            open_questions=["Which matched fractions preserve or lose a candidate functional signal?"], **common),
        DesignGap(gap_id="design-gap-isolation-fractionation", title="Isolation and fractionation",
            question="Which bounded isolation or fractionation comparison could clarify product identity and recovery tradeoffs?",
            domain="fractionation", blocking_value=5, priority=5, mechanistic_relevance=4,
            rationale="Canonical product purification and fractionation state is unresolved.",
            open_questions=["Which process comparison is analytically discriminating and manufacturable?"], **common),
        DesignGap(gap_id="design-gap-mechanism-potency", title="Mechanism-linked potency",
            question="Which non-clinical functional readout could discriminate a mechanism-linked product signal from particle abundance alone?",
            domain="potency", blocking_value=5,
            rationale="Canonical Manufacturing records potency as an evidence gap and prohibits particle count as established potency.",
            priority=5, mechanistic_relevance=5, open_questions=["Which functional readout can be linked to a product attribute?"], **common),
        DesignGap(gap_id="design-gap-mechanism", title="Mechanism of action",
            question="Which causal link can be tested without claiming an established SGL-001 mechanism?",
            domain="mechanism", blocking_value=4, priority=4, mechanistic_relevance=5,
            rationale="The active biology and causal mechanism remain hypotheses.",
            open_questions=["Which competing explanation can one experiment distinguish?"], **common),
        DesignGap(gap_id="design-gap-stability", title="Stability-indicating attributes",
            question="Which exploratory attributes could reveal loss of product integrity during formulation and storage studies?",
            domain="stability", blocking_value=4,
            rationale="No canonical SGL-001 stability program or verified shelf life exists.",
            priority=4, mechanistic_relevance=3, open_questions=["Which attributes are stability-indicating?"], **common),
        DesignGap(gap_id="design-gap-intranasal-compatibility", title="Intranasal formulation compatibility",
            question="How should formulation and device compatibility be tested without assuming preserved EV identity or activity?",
            domain="formulation", blocking_value=4,
            rationale="Vehicle, stabilizer, and device compatibility remain unresolved canonical actions.",
            priority=4, mechanistic_relevance=4, open_questions=["Which compatibility test best protects interpretability?"], **common),
        DesignGap(gap_id="design-gap-manufacturing-process", title="Manufacturing process",
            question="Which process-stage comparison could reveal sensitivity of an exploratory product signature?",
            domain="process", blocking_value=5, priority=5, mechanistic_relevance=4,
            rationale="Most canonical process stages remain not defined or proposal-only.",
            open_questions=["Which stage is most likely to alter identity or functional signal?"], **common),
        DesignGap(gap_id="design-gap-lot-comparability", title="Lot comparability",
            question="Which exploratory fingerprint could be assessed across future representative lots without becoming a premature release specification?",
            domain="reproducibility", blocking_value=4,
            rationale="Canonical Manufacturing records no lots and lot reproducibility as an evidence gap.",
            priority=4, mechanistic_relevance=3, open_questions=["Which future fingerprint supports comparability without becoming a premature specification?"], **common),
        DesignGap(gap_id="design-gap-scale-control", title="Scale-up and control strategy",
            question="Which scale-sensitive attribute and proposed control should be evaluated before representative production studies?",
            domain="manufacturing", blocking_value=5, priority=5, mechanistic_relevance=3,
            rationale="Scale-up, source control, and process control remain canonical evidence gaps.",
            open_questions=["Which control can distinguish scale effect from analytical noise?"], **common),
    ]
    return DesignLabWorkspace(schema_version="1.1", design_gaps=gaps, updated_at=now)


def migrate_design_lab(workspace: DesignLabWorkspace) -> DesignLabWorkspace:
    """Deterministically add persistent themes and exploration metadata."""
    seed = initial_design_lab(workspace.updated_at)
    hypotheses_by_theme: dict[str, list[DesignHypothesis]] = {}
    migrated_hypotheses = []
    for item in workspace.reviewed_hypotheses:
        theme_id = item.theme_id or item.selected_gap_id
        sequence = len(hypotheses_by_theme.get(theme_id, [])) + 1
        migrated = item.model_copy(update={
            "theme_id": theme_id,
            "sequence_within_theme": item.sequence_within_theme or sequence,
            "novelty_statement": item.novelty_statement or "First recorded hypothesis for this persistent research theme.",
        })
        hypotheses_by_theme.setdefault(theme_id, []).append(migrated)
        migrated_hypotheses.append(migrated)
    existing = {item.gap_id: item for item in workspace.design_gaps}
    themes = []
    for seeded in seed.design_gaps:
        old = existing.get(seeded.gap_id)
        source = old or seeded
        history = hypotheses_by_theme.get(seeded.gap_id, [])
        themes.append(source.model_copy(update={
            "title": seeded.title, "question": seeded.question,
            "domain": seeded.domain, "rationale": seeded.rationale,
            "status": "open", "times_explored": len(history),
            "last_explored_at": history[-1].created_at if history else None,
            "latest_hypothesis_id": history[-1].hypothesis_id if history else None,
            "hypothesis_ids": [item.hypothesis_id for item in history],
            "open_questions": source.open_questions or seeded.open_questions,
            "priority": source.priority if old and "priority" in old.model_fields_set else seeded.priority,
            "mechanistic_relevance": source.mechanistic_relevance if old and "mechanistic_relevance" in old.model_fields_set else seeded.mechanistic_relevance,
        }))
    candidates = [item.model_copy(update={
        "source_hypothesis_ids": list(dict.fromkeys([item.source_hypothesis_id, *item.source_hypothesis_ids])),
        "measurement_concept": item.measurement_concept or item.name,
    }) for item in workspace.product_signature_candidates]
    migrated = workspace.model_copy(update={
        "schema_version": "1.1", "reviewed_hypotheses": migrated_hypotheses,
        "product_signature_candidates": candidates, "design_gaps": themes,
    })
    return DesignLabWorkspace.model_validate(migrated.model_dump(mode="python"))


def select_design_gap(workspace: DesignLabWorkspace, *, now: datetime | None = None) -> tuple[DesignGap, str]:
    themes = workspace.design_gaps
    if not themes:
        raise ValueError("no persistent product-design theme is available")
    selected_at = now or workspace.updated_at
    recent = [item.gap_id for item in workspace.recent_runs[-2:]]
    def score(gap: DesignGap):
        base = (gap.blocking_value * 5 + gap.product_definition_relevance * 4
                + gap.manufacturing_relevance * 3 + gap.discriminating_value * 3
                + gap.testability * 2 + gap.evidence_availability
                + gap.mechanistic_relevance * 3 + gap.priority * 4)
        unexplored = 500 if gap.times_explored == 0 else 0
        stale_days = ((selected_at - gap.last_explored_at).days if gap.last_explored_at else 0)
        recency_penalty = 250 if gap.gap_id in recent and gap.human_priority_override is None else 0
        override = (gap.human_priority_override or 0) * 1000
        return override + unexplored + base + min(max(stale_days, 0), 365) * 3 - gap.times_explored * 60 - recency_penalty
    selected = max(themes, key=lambda item: (score(item), -themes.index(item)))
    return selected, (
        f"Selected persistent theme using balanced score {score(selected)}: development relevance, "
        f"manufacturing relevance, mechanistic relevance, exploration count ({selected.times_explored}), "
        f"staleness, recent diversity, and human override ({selected.human_priority_override})."
    )


def validate_evidence_ids(value: Any, allowed: set[str]) -> None:
    ids: list[str] = []
    def walk(item: Any, key: str | None = None):
        if isinstance(item, BaseModel):
            walk(item.model_dump(mode="python"))
        elif isinstance(item, dict):
            for name, child in item.items():
                walk(child, name)
        elif isinstance(item, list):
            if key and key.endswith("evidence_ids"):
                ids.extend(str(child) for child in item)
            else:
                for child in item:
                    walk(child, key)
    walk(value)
    unknown = sorted(set(ids) - allowed)
    if unknown:
        raise ValueError(f"Design Lab references unknown canonical evidence: {unknown}")


def bind_proposal_metadata(
    proposal: DesignProposal,
    *,
    run_id: str,
    selected_theme: DesignGap,
    sequence_within_theme: int,
) -> DesignProposal:
    """Bind orchestration-owned proposal metadata without changing scientific content."""

    hypothesis_id = f"design-hypothesis-{run_id}"
    experiment = proposal.experiment.model_copy(
        update={"experiment_id": f"design-experiment-{run_id}"}
    )
    candidates = [
        candidate.model_copy(update={
            "attribute_id": f"design-signature-{run_id}-{index}",
            "source_hypothesis_id": hypothesis_id,
        })
        for index, candidate in enumerate(proposal.candidate_quality_attributes, start=1)
    ]
    candidate_ids = [candidate.attribute_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate system-bound signature candidate ID")
    bound = proposal.model_copy(update={
        "primary_domain": selected_theme.domain,
        "theme_id": selected_theme.gap_id,
        "sequence_within_theme": sequence_within_theme,
        "experiment": experiment,
        "candidate_quality_attributes": candidates,
    })
    return DesignProposal.model_validate(bound.model_dump(mode="python"))


def _semantic_key(proposal: DesignProposal) -> str:
    text = " ".join((proposal.title, proposal.design_question, proposal.proposed_product_change_or_attribute))
    return " ".join("".join(ch.casefold() if ch.isalnum() else " " for ch in text).split())


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _tokens(value: str) -> set[str]:
    return set(_normalized(value).split())


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a or b else 1.0


def _mechanism_text(value: DesignProposal | DesignHypothesis) -> str:
    return " ".join(
        [node.statement for node in value.causal_chain.nodes]
        + [edge.uncertainty + " " + (edge.competing_explanation or "") for edge in value.causal_chain.edges]
    )


def _experiment_text(value: DesignProposal | DesignHypothesis) -> str:
    experiment = value.experiment if isinstance(value, DesignProposal) else value.minimum_discriminating_experiment
    if experiment is None:
        return ""
    return " ".join((experiment.question, experiment.hypothesis_tested, experiment.comparator,
        experiment.control, experiment.assay, experiment.primary_readout,
        experiment.success_criterion, experiment.falsification_outcome))


def novelty_conflicts(proposal: DesignProposal, existing: list[DesignHypothesis]) -> list[str]:
    conflicts = []
    proposal_key = _semantic_key(proposal)
    for prior in existing:
        prior_key = _normalized(" ".join((prior.title, prior.design_question, prior.proposed_product_change_or_attribute)))
        attribute_similarity = _similarity(proposal.proposed_product_change_or_attribute, prior.proposed_product_change_or_attribute)
        mechanism_similarity = _similarity(_mechanism_text(proposal), _mechanism_text(prior))
        experiment_similarity = _similarity(_experiment_text(proposal), _experiment_text(prior))
        overall_similarity = _similarity(proposal_key, prior_key)
        same_theme = proposal.theme_id == (prior.theme_id or prior.selected_gap_id)
        if proposal_key == prior_key:
            conflicts.append(f"exact duplicate of {prior.hypothesis_id}")
        elif same_theme and attribute_similarity >= .88 and experiment_similarity >= .85:
            conflicts.append(f"same product intervention and experiment as {prior.hypothesis_id}")
        elif same_theme and mechanism_similarity >= .9 and experiment_similarity >= .85:
            conflicts.append(f"same mechanism and cosmetic experiment variant as {prior.hypothesis_id}")
        elif same_theme and overall_similarity >= .88 and experiment_similarity >= .75:
            conflicts.append(f"simple rewording with no new discriminating test versus {prior.hypothesis_id}")
    return conflicts


def _signature_key(value) -> tuple[str, str, str]:
    concept = value.measurement_concept or value.name
    return (_normalized(value.name), value.group.value, f"{value.role.value}:{_normalized(concept)}")


def merge_signature_candidates(existing, proposed):
    """Keep one display record while accumulating supporting hypothesis references."""
    merged = list(existing)
    index = {_signature_key(item): position for position, item in enumerate(merged)}
    id_map: dict[str, str] = {}
    for item in proposed:
        key = _signature_key(item)
        if key not in index:
            normalized = item.model_copy(update={
                "source_hypothesis_ids": list(dict.fromkeys([item.source_hypothesis_id, *item.source_hypothesis_ids])),
                "measurement_concept": item.measurement_concept or item.name,
            })
            index[key] = len(merged)
            merged.append(normalized)
            id_map[item.attribute_id] = item.attribute_id
            continue
        position = index[key]
        current = merged[position]
        merged[position] = current.model_copy(update={
            "evidence_ids": list(dict.fromkeys([*current.evidence_ids, *item.evidence_ids])),
            "source_hypothesis_ids": list(dict.fromkeys([
                current.source_hypothesis_id, *current.source_hypothesis_ids,
                item.source_hypothesis_id, *item.source_hypothesis_ids,
            ])),
        })
        id_map[item.attribute_id] = current.attribute_id
    return merged, id_map


class DesignLabOrchestrator:
    def __init__(self, *, client: ModelClient, root: Path, now_factory=_now) -> None:
        self.client, self.root, self.now_factory = client, root, now_factory
        self._repair_used = False

    def _generate(self, instructions: str, payload: dict[str, Any], output_type: type[T], store: RunStore, stage: str) -> T:
        text = _json(payload)
        try:
            return self.client.generate(instructions=instructions, input_text=text, output_type=output_type)
        except StructuredOutputError as error:
            if self._repair_used:
                raise
            self._repair_used = True
            store.write_json(f"private-{stage}-validation-error.json", {
                "stage": stage, "conflicts": error.conflicts, "repair_attempted": True,
            })
            repair = getattr(self.client, "repair", None)
            if repair is None:
                raise
            return repair(
                instructions=f"{DESIGN_REPAIR}\nExact validation errors: {error.conflicts}",
                input_text=text, output_type=output_type,
            )

    def run(self, *, run_id: str | None = None) -> DesignHypothesis:
        self._repair_used = False
        active_id, created = run_id or new_run_id(), self.now_factory()
        store = RunStore(self.root / "design-runs", active_id)
        try:
            state = _load(self.root / "state/signal-state.json", SignalState)
            asset = _load(self.root / "state/asset-development.json", TherapeuticAssetWorkspace)
            docket = _load(self.root / "state/development-docket.json", DevelopmentDocket)
            history = _load(self.root / "state/live-runs.json", LiveRunHistory)
            workspace_path = self.root / "state/design-lab.json"
            workspace = migrate_design_lab(
                _load(workspace_path, DesignLabWorkspace) if workspace_path.exists() else initial_design_lab(created)
            )
            gap, why = select_design_gap(workspace, now=created)
            allowed = {item.evidence_id for item in state.evidence}
            cargo_focus = set(asset.cargo.operator_focus_candidate_ids)
            context = {
                "program": state.program, "selected_gap": gap, "why_selected": why,
                "canonical_evidence": state.evidence, "canonical_claims": state.claims,
                "cargo": {
                    "operator_focus_candidate_ids": sorted(cargo_focus),
                    "focus_candidates": [x for x in asset.cargo.candidates if x.cargo_candidate_id in cargo_focus],
                    "pathways": asset.cargo.pathways,
                },
                "formulation": {
                    "candidates": [x for x in asset.formulation.candidates if x.status.value in {"focus", "benchmark"}],
                    "attributes": asset.formulation.attributes,
                },
                "manufacturing": {
                    "product_definition": asset.manufacturing.product_definition,
                    "quality_attributes": asset.manufacturing.quality_attributes,
                    "potency_strategy": asset.manufacturing.potency_strategy,
                    "readiness": asset.manufacturing.readiness,
                    "risks": asset.manufacturing.risks,
                    "next_actions": asset.manufacturing.next_actions,
                },
                "docket": [x for x in docket.matters if x.status.value in {"open", "selected"}],
                "recent_determinations": [{
                    "run_id": x.run_id, "matter_id": x.selected_matter.matter_id,
                    "determination": x.chair_determination, "state_changed": x.state_changed,
                    "what_changed": x.what_changed, "next_action": x.next_action,
                } for x in history.runs[-3:]],
                "allowed_evidence_ids": sorted(allowed),
                "required_hypothesis_id": f"design-hypothesis-{active_id}",
                "required_experiment_id": f"design-experiment-{active_id}",
                "required_theme_id": gap.gap_id,
                "required_sequence_within_theme": gap.times_explored + 1,
                "prior_hypotheses": [{
                    "hypothesis_id": item.hypothesis_id, "theme_id": item.theme_id,
                    "title": item.title, "design_question": item.design_question,
                    "proposed_product_change_or_attribute": item.proposed_product_change_or_attribute,
                    "causal_chain": item.causal_chain,
                    "minimum_discriminating_experiment": item.minimum_discriminating_experiment,
                    "candidate_quality_attributes_affected": item.candidate_quality_attributes_affected,
                } for item in workspace.reviewed_hypotheses],
            }
            store.write_json("00-run-input.json", context)
            store.write_json("01-selected-gap.json", {"gap": gap, "why_selected": why})
            expected_hypothesis_id = f"design-hypothesis-{active_id}"
            expected_experiment_id = f"design-experiment-{active_id}"
            required_sequence = gap.times_explored + 1
            proposal = bind_proposal_metadata(
                self._generate(DESIGN_SCIENTIST, context, DesignProposal, store, "proposal"),
                run_id=active_id,
                selected_theme=gap,
                sequence_within_theme=required_sequence,
            )
            def validate_proposal(value: DesignProposal) -> None:
                validate_evidence_ids(value, allowed)
                if value.experiment.experiment_id != expected_experiment_id:
                    raise ValueError("experiment ID does not match the immutable run ID")
                if value.theme_id != gap.gap_id or value.sequence_within_theme != required_sequence:
                    raise ValueError("proposal theme or sequence does not match selected persistent theme")
                if value.primary_domain != gap.domain:
                    raise ValueError("proposal primary domain must match the selected persistent theme")
                prior_ids = {item.hypothesis_id for item in workspace.reviewed_hypotheses}
                candidate_ids = [item.attribute_id for item in value.candidate_quality_attributes]
                expected_candidate_ids = [
                    f"design-signature-{active_id}-{index}"
                    for index in range(1, len(candidate_ids) + 1)
                ]
                if len(candidate_ids) != len(set(candidate_ids)):
                    raise ValueError("duplicate system-bound signature candidate ID")
                if candidate_ids != expected_candidate_ids:
                    raise ValueError("signature candidate IDs do not match immutable run metadata")
                if set(value.distinguished_from_hypothesis_ids) - prior_ids:
                    raise ValueError("novelty statement references unknown prior hypotheses")
                same_theme = set(gap.hypothesis_ids)
                if same_theme and not same_theme.intersection(value.distinguished_from_hypothesis_ids):
                    raise ValueError("revisited theme must distinguish the proposal from prior theme hypotheses")
                for candidate in value.candidate_quality_attributes:
                    if candidate.source_hypothesis_id != expected_hypothesis_id:
                        raise ValueError("signature candidate must reference this run hypothesis")
                    if set(candidate.source_hypothesis_ids) - (prior_ids | {expected_hypothesis_id}):
                        raise ValueError("signature candidate references unknown prior hypotheses")
                    if candidate.role.value == "validated_release_test":
                        raise ValueError("autonomous Design Lab cannot assign validated release tests")
            validate_proposal(proposal)
            conflicts = novelty_conflicts(proposal, workspace.reviewed_hypotheses)
            if conflicts:
                if self._repair_used:
                    raise ValueError(f"duplicate design hypothesis: {conflicts}")
                self._repair_used = True
                store.write_json("private-proposal-novelty-conflict.json", {
                    "conflicts": conflicts, "repair_attempted": True,
                })
                repair = getattr(self.client, "repair", None)
                if repair is None:
                    raise ValueError(f"duplicate design hypothesis: {conflicts}")
                proposal = bind_proposal_metadata(
                    repair(
                        instructions=(f"{DESIGN_REPAIR}\nNovelty conflicts: {conflicts}. "
                            "Return a materially distinct testable proposal for the same theme."),
                        input_text=_json(context),
                        output_type=DesignProposal,
                    ),
                    run_id=active_id,
                    selected_theme=gap,
                    sequence_within_theme=required_sequence,
                )
                validate_proposal(proposal)
                remaining = novelty_conflicts(proposal, workspace.reviewed_hypotheses)
                if remaining:
                    raise ValueError(f"duplicate design hypothesis after repair: {remaining}")
            store.write_json("02-design-proposal.json", proposal)
            review_context = {"proposal": proposal, "allowed_evidence_ids": sorted(allowed), "canonical_evidence": state.evidence}
            evidence = self._generate(EVIDENCE_VERIFIER, review_context, DesignReview, store, "evidence-review")
            cmc = self._generate(CMC_REVIEWER, review_context, DesignReview, store, "cmc-review")
            mechanism = self._generate(MECHANISM_REVIEWER, review_context, DesignReview, store, "mechanism-review")
            adversary = self._generate(DESIGN_ADVERSARY, review_context, DesignAdversaryReview, store, "adversary")
            for output in (evidence, cmc, mechanism, adversary):
                validate_evidence_ids(output, allowed)
            store.write_json("03-evidence-review.json", evidence)
            store.write_json("04-cmc-review.json", cmc)
            store.write_json("05-mechanism-review.json", mechanism)
            store.write_json("06-adversary.json", adversary)
            chair = self._generate(DESIGN_CHAIR, {
                "proposal": proposal, "evidence_review": evidence, "cmc_review": cmc,
                "mechanism_review": mechanism, "adversary": adversary,
            }, DesignChairClassification, store, "chair")
            determination = chair.determination
            if not evidence.supported:
                determination = DesignDetermination.NEEDS_EVIDENCE
            elif not cmc.supported and determination is DesignDetermination.PROPOSED_FOR_TESTING:
                determination = DesignDetermination.NEEDS_MANUFACTURING
            findings = [ReviewerFinding(role=role, conclusion=value.conclusion,
                supported=value.supported, evidence_ids=value.evidence_ids,
                evidence_gap=value.evidence_gap, concerns=value.concerns)
                for role, value in (("evidence_verifier", evidence), ("cmc_manufacturing", cmc), ("mechanism", mechanism))]
            status = "rejected" if determination is DesignDetermination.REJECTED else "parked" if determination is DesignDetermination.PARKED else "reviewed"
            merged_candidates, candidate_id_map = merge_signature_candidates(
                workspace.product_signature_candidates, proposal.candidate_quality_attributes
            )
            hypothesis = DesignHypothesis(
                hypothesis_id=expected_hypothesis_id, program_id=state.program.program_id,
                run_id=active_id, created_at=created, title=proposal.title,
                design_question=proposal.design_question, primary_domain=proposal.primary_domain,
                secondary_domains=proposal.secondary_domains, selected_gap_id=gap.gap_id,
                proposed_product_change_or_attribute=proposal.proposed_product_change_or_attribute,
                biological_rationale=proposal.biological_rationale,
                manufacturing_rationale=proposal.manufacturing_rationale, causal_chain=proposal.causal_chain,
                expected_measurable_effect=proposal.expected_measurable_effect,
                supporting_evidence_ids=proposal.supporting_evidence_ids,
                contradicting_evidence_ids=proposal.contradicting_evidence_ids,
                explicit_inferences=proposal.explicit_inferences, assumptions=proposal.assumptions,
                competing_explanations=proposal.competing_explanations,
                manufacturability_assessment=proposal.manufacturability_assessment,
                measurement_strategy=proposal.measurement_strategy,
                candidate_quality_attributes_affected=[candidate_id_map[x.attribute_id] for x in proposal.candidate_quality_attributes],
                proposed_potency_relationship=proposal.proposed_potency_relationship,
                principal_risks=proposal.principal_risks, falsification_criteria=proposal.falsification_criteria,
                minimum_discriminating_experiment=None if determination is DesignDetermination.REJECTED else proposal.experiment,
                dependencies=proposal.dependencies, human_decisions_required=proposal.human_decisions_required,
                reviewer_findings=findings, adversary_objection=adversary.strongest_objection,
                chair_rationale=chair.rationale, determination=determination, status=status,
                novelty_statement=proposal.novelty_statement,
                distinguished_from_hypothesis_ids=proposal.distinguished_from_hypothesis_ids,
                theme_id=gap.gap_id, sequence_within_theme=gap.times_explored + 1,
            )
            validate_evidence_ids(hypothesis, allowed)
            store.write_json("07-chair-classification.json", chair)
            store.write_json("08-reviewed-hypothesis.json", hypothesis)
            gap_updates = [item.model_copy(update={
                "status": "open", "times_explored": item.times_explored + 1,
                "last_explored_at": created, "latest_hypothesis_id": hypothesis.hypothesis_id,
                "hypothesis_ids": [*item.hypothesis_ids, hypothesis.hypothesis_id],
            }) if item.gap_id == gap.gap_id else item for item in workspace.design_gaps]
            updated = workspace.model_copy(update={
                "current_design_question": hypothesis.design_question,
                "reviewed_hypotheses": [*workspace.reviewed_hypotheses, hypothesis],
                "proposed_experiments": workspace.proposed_experiments + ([proposal.experiment] if determination is not DesignDetermination.REJECTED else []),
                "parked_hypothesis_ids": workspace.parked_hypothesis_ids + ([hypothesis.hypothesis_id] if status == "parked" else []),
                "rejected_hypothesis_ids": workspace.rejected_hypothesis_ids + ([hypothesis.hypothesis_id] if status == "rejected" else []),
                "product_signature_candidates": merged_candidates,
                "design_gaps": gap_updates,
                "recent_runs": [*workspace.recent_runs, DesignRunSummary(run_id=active_id,
                    hypothesis_id=hypothesis.hypothesis_id, gap_id=gap.gap_id,
                    determination=determination, created_at=created)],
                "updated_at": created,
            })
            updated = DesignLabWorkspace.model_validate(updated.model_dump(mode="python"))
            # Build and validate both outputs before either canonical/public destination changes.
            public = build_current_public_state(self.root, generated_at=created).model_copy(
                update={"design_lab": export_design_lab(updated)}
            )
            type(public).model_validate(public.model_dump(mode="python", by_alias=True))
            usage = getattr(self.client, "usage_records", None)
            if usage is not None:
                store.write_json("09-private-api-usage.json", {
                    "run_id": active_id, "attempts": usage,
                })
            publish_json(workspace_path, updated)
            publish_json(self.root / "public/signal-state.json", public)
            return hypothesis
        except Exception as error:
            store.write_json("99-run-failed.json", {"error_type": type(error).__name__, "message": str(error)})
            raise
