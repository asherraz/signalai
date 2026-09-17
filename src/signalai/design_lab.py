"""Bounded, review-gated SGL-001 Product Design Lab."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, model: type[T]) -> T:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def initial_design_lab(now: datetime) -> DesignLabWorkspace:
    common = dict(testability=4, product_definition_relevance=5, manufacturing_relevance=5,
                  evidence_availability=2, discriminating_value=5)
    gaps = [
        DesignGap(gap_id="design-gap-product-identity", title="EV versus non-EV product identity",
            question="Which measurable composition distinction can discriminate a secretome-retaining-EV product from a small-EV preparation?",
            domain="product_identity", blocking_value=5,
            rationale="Canonical Manufacturing records exact drug-substance identity and fractionation as unresolved.", **common),
        DesignGap(gap_id="design-gap-source-cell", title="Source-cell definition",
            question="Which source-cell attributes should be evaluated for their relationship to a reproducible SGL-001 product signature?",
            domain="cell_source", blocking_value=5,
            rationale="Canonical Manufacturing records source qualification and cell-bank strategy as evidence gaps.", **common),
        DesignGap(gap_id="design-gap-mechanism-potency", title="Mechanism-linked potency",
            question="Which non-clinical functional readout could discriminate a mechanism-linked product signal from particle abundance alone?",
            domain="potency", blocking_value=5,
            rationale="Canonical Manufacturing records potency as an evidence gap and prohibits particle count as established potency.", **common),
        DesignGap(gap_id="design-gap-stability", title="Stability-indicating attributes",
            question="Which exploratory attributes could reveal loss of product integrity during formulation and storage studies?",
            domain="stability", blocking_value=4,
            rationale="No canonical SGL-001 stability program or verified shelf life exists.", **common),
        DesignGap(gap_id="design-gap-intranasal-compatibility", title="Intranasal formulation compatibility",
            question="How should formulation and device compatibility be tested without assuming preserved EV identity or activity?",
            domain="formulation", blocking_value=4,
            rationale="Vehicle, stabilizer, and device compatibility remain unresolved canonical actions.", **common),
        DesignGap(gap_id="design-gap-lot-comparability", title="Lot comparability",
            question="Which exploratory fingerprint could be assessed across future representative lots without becoming a premature release specification?",
            domain="reproducibility", blocking_value=4,
            rationale="Canonical Manufacturing records no lots and lot reproducibility as an evidence gap.", **common),
    ]
    return DesignLabWorkspace(design_gaps=gaps, updated_at=now)


def select_design_gap(workspace: DesignLabWorkspace) -> tuple[DesignGap, str]:
    open_gaps = [gap for gap in workspace.design_gaps if gap.status == "open"]
    if not open_gaps:
        raise ValueError("no open product-design gap is available")
    def score(gap: DesignGap):
        return (gap.blocking_value * 5 + gap.product_definition_relevance * 4
                + gap.manufacturing_relevance * 3 + gap.discriminating_value * 3
                + gap.testability * 2 + gap.evidence_availability)
    selected = max(open_gaps, key=score)
    return selected, (
        f"Selected for development-blocking value ({selected.blocking_value}/5), product-definition "
        f"relevance ({selected.product_definition_relevance}/5), manufacturing relevance "
        f"({selected.manufacturing_relevance}/5), and discriminating value ({selected.discriminating_value}/5)."
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


def _semantic_key(proposal: DesignProposal) -> str:
    text = " ".join((proposal.title, proposal.design_question, proposal.proposed_product_change_or_attribute))
    return " ".join("".join(ch.casefold() if ch.isalnum() else " " for ch in text).split())


class DesignLabOrchestrator:
    def __init__(self, *, client: ModelClient, root: Path, now_factory=_now) -> None:
        self.client, self.root, self.now_factory = client, root, now_factory
        self._repair_used = False

    def _generate(self, instructions: str, payload: dict[str, Any], output_type: type[T], store: RunStore, stage: str) -> T:
        text = json.dumps(payload, default=str, sort_keys=True)
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
            workspace = _load(workspace_path, DesignLabWorkspace) if workspace_path.exists() else initial_design_lab(created)
            gap, why = select_design_gap(workspace)
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
            }
            store.write_json("00-run-input.json", context)
            store.write_json("01-selected-gap.json", {"gap": gap, "why_selected": why})
            proposal = self._generate(DESIGN_SCIENTIST, context, DesignProposal, store, "proposal")
            validate_evidence_ids(proposal, allowed)
            expected_hypothesis_id = f"design-hypothesis-{active_id}"
            expected_experiment_id = f"design-experiment-{active_id}"
            if proposal.experiment.experiment_id != expected_experiment_id:
                raise ValueError("experiment ID does not match the immutable run ID")
            for candidate in proposal.candidate_quality_attributes:
                if candidate.source_hypothesis_id != expected_hypothesis_id:
                    raise ValueError("signature candidate must reference this run hypothesis")
                if candidate.role.value == "validated_release_test":
                    raise ValueError("autonomous Design Lab cannot assign validated release tests")
            if proposal.design_question != gap.question or proposal.primary_domain is not gap.domain:
                raise ValueError("proposal must answer the selected design gap")
            existing_keys = {
                " ".join("".join(ch.casefold() if ch.isalnum() else " " for ch in
                    " ".join((item.title, item.design_question, item.proposed_product_change_or_attribute))).split())
                for item in workspace.reviewed_hypotheses
            }
            if _semantic_key(proposal) in existing_keys:
                raise ValueError("duplicate design hypothesis")
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
                candidate_quality_attributes_affected=[x.attribute_id for x in proposal.candidate_quality_attributes],
                proposed_potency_relationship=proposal.proposed_potency_relationship,
                principal_risks=proposal.principal_risks, falsification_criteria=proposal.falsification_criteria,
                minimum_discriminating_experiment=None if determination is DesignDetermination.REJECTED else proposal.experiment,
                dependencies=proposal.dependencies, human_decisions_required=proposal.human_decisions_required,
                reviewer_findings=findings, adversary_objection=adversary.strongest_objection,
                chair_rationale=chair.rationale, determination=determination, status=status,
            )
            validate_evidence_ids(hypothesis, allowed)
            store.write_json("07-chair-classification.json", chair)
            store.write_json("08-reviewed-hypothesis.json", hypothesis)
            gap_updates = [item.model_copy(update={"status": "reviewed"}) if item.gap_id == gap.gap_id else item for item in workspace.design_gaps]
            updated = workspace.model_copy(update={
                "current_design_question": hypothesis.design_question,
                "reviewed_hypotheses": [*workspace.reviewed_hypotheses, hypothesis],
                "proposed_experiments": workspace.proposed_experiments + ([proposal.experiment] if determination is not DesignDetermination.REJECTED else []),
                "parked_hypothesis_ids": workspace.parked_hypothesis_ids + ([hypothesis.hypothesis_id] if status == "parked" else []),
                "rejected_hypothesis_ids": workspace.rejected_hypothesis_ids + ([hypothesis.hypothesis_id] if status == "rejected" else []),
                "product_signature_candidates": [*workspace.product_signature_candidates, *proposal.candidate_quality_attributes],
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
