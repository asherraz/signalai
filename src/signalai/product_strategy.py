"""Deterministic scoring and bounded Product Strategy Council orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter

from signalai.client import ModelClient
from signalai.schemas import SignalState
from signalai.schemas.product_strategy import (
    ArchitectureAssessment, ArchitectureDimension, ArchitectureDimensionAssessment,
    ArchitectureDisposition, ArchitectureHardGate, AssessmentSourceType,
    DIMENSION_WEIGHTS, CONFIDENCE_FACTORS, HardGateState,
    ProductArchitectureCandidate, ProductStrategyWorkspace,
    StrategyAdversaryReview, StrategyAssessmentHistoryEntry, StrategyChairRecommendation,
    StrategyConfidence, StrategyDetermination, StrategyDeterminationType,
    StrategySpecialistAssessment, TherapeuticObjective,
)
from signalai.storage import RunStore, new_run_id, publish_json


DIMENSION_TITLES = {
    ArchitectureDimension.HUMAN_FEASIBILITY: ("Near-term human-data feasibility", "Practical path to legitimate, supervised human development."),
    ArchitectureDimension.SAFETY: ("Safety readiness", "Evidence and controls needed to justify further development."),
    ArchitectureDimension.PRODUCT_QC: ("Product definition and QC", "Ability to define identity, quality and reproducibility."),
    ArchitectureDimension.BIOLOGY: ("Biological rationale and impact", "Strength and relevance of the biological hypothesis."),
    ArchitectureDimension.MANUFACTURING: ("Manufacturing readiness", "Traceability and readiness of the production approach."),
    ArchitectureDimension.SCALABILITY: ("Scalability and economics", "Potential operational scalability without implying commercial success."),
    ArchitectureDimension.REGULATORY: ("Regulatory clarity and data portability", "Clarity and portability of a legitimate development package."),
}
GATE_NAMES = [
    "legitimate human-study pathway", "adequate preclinical safety basis",
    "traceable manufacturing process", "defined product identity", "lot-release framework",
    "sterility and contaminant controls", "interpretable clinical protocol",
    "ethics and human oversight", "adverse-event monitoring",
]
SPECIALIST_ROLES = {
    ArchitectureDimension.HUMAN_FEASIBILITY: "Human Evidence Path",
    ArchitectureDimension.SAFETY: "Safety",
    ArchitectureDimension.PRODUCT_QC: "Product Definition and QC",
    ArchitectureDimension.BIOLOGY: "Biology and MOA",
    ArchitectureDimension.MANUFACTURING: "CMC and Manufacturing",
    ArchitectureDimension.SCALABILITY: "Scalability and Economics",
    ArchitectureDimension.REGULATORY: "Regulatory and Jurisdiction",
}


def strategy_input_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in ("state/signal-state.json", "state/asset-development.json"):
        digest.update(relative.encode())
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()


def score_dimension(*, candidate_id: str, dimension: ArchitectureDimension, rating: int,
                    confidence: StrategyConfidence, evidence_status: str, rationale: str,
                    uncertainty: str, evidence_ids: list[str], source_type: AssessmentSourceType,
                    assessment_id: str | None = None) -> ArchitectureDimensionAssessment:
    weight = DIMENSION_WEIGHTS[dimension]
    potential = weight * rating / 5
    return ArchitectureDimensionAssessment(
        assessment_id=assessment_id or f"assessment-{candidate_id}-{dimension.value}",
        candidate_id=candidate_id, dimension=dimension, weight=weight, rating=rating,
        confidence=confidence, evidence_status=evidence_status, rationale=rationale,
        uncertainty=uncertainty, evidence_ids=evidence_ids, source_type=source_type,
        potential_contribution=potential,
        confidence_adjusted_contribution=potential * CONFIDENCE_FACTORS[confidence],
    )


def score_candidate(candidate: ProductArchitectureCandidate, assessments: list[ArchitectureDimensionAssessment],
                    *, assessed_at: datetime) -> ProductArchitectureCandidate:
    return candidate.model_copy(update={
        "dimension_assessments": assessments,
        "raw_potential_score": sum(item.potential_contribution for item in assessments),
        "confidence_adjusted_decision_score": sum(item.confidence_adjusted_contribution for item in assessments),
        "last_assessed_at": assessed_at,
        "evidence_ids": list(dict.fromkeys(eid for item in assessments for eid in item.evidence_ids)),
    })


def _initial_candidate(candidate_id: str, designation: str, name: str, description: str,
                       architecture_class: str, role: str, disposition: ArchitectureDisposition,
                       ratings: list[int], confidences: list[StrategyConfidence], now: datetime,
                       evidence_ids: list[str], advantage: str, obstacle: str, unknowns: list[str],
                       action: str) -> ProductArchitectureCandidate:
    assessments = []
    for dimension, rating, confidence in zip(ArchitectureDimension, ratings, confidences, strict=True):
        assessments.append(score_dimension(
            candidate_id=candidate_id, dimension=dimension, rating=rating, confidence=confidence,
            evidence_status="Existing repository evidence is indirect or architecture-analog evidence.",
            rationale=f"Conservative initial {dimension.value.replace('_', ' ')} assessment for {designation}; no candidate-specific development result is claimed.",
            uncertainty="SGL-001 architecture-specific data are absent or incomplete.",
            evidence_ids=evidence_ids, source_type=AssessmentSourceType.INFERENCE,
        ))
    gates = [ArchitectureHardGate(
        gate_id=f"gate-{candidate_id}-{index}", candidate_id=candidate_id, name=name,
        status=HardGateState.UNRESOLVED,
        rationale="No complete candidate-specific gate package is recorded in canonical state.",
        evidence_ids=[],
    ) for index, name in enumerate(GATE_NAMES, start=1)]
    base = ProductArchitectureCandidate(
        candidate_id=candidate_id, program_id="SGL-001", designation=designation, name=name,
        short_description=description, architecture_class=architecture_class, strategic_role=role,
        lifecycle_status=disposition, current_disposition=disposition, hard_gates=gates,
        dimension_assessments=assessments, raw_potential_score=sum(x.potential_contribution for x in assessments),
        confidence_adjusted_decision_score=sum(x.confidence_adjusted_contribution for x in assessments),
        overall_confidence=StrategyConfidence.LOW, principal_advantage=advantage,
        largest_obstacle=obstacle, critical_unknowns=unknowns,
        next_discriminating_action=action, evidence_ids=evidence_ids, last_assessed_at=now,
    )
    return ProductArchitectureCandidate.model_validate(base.model_dump(mode="python"))


def initial_product_strategy(root: Path, *, now: datetime | None = None) -> ProductStrategyWorkspace:
    timestamp = now or datetime.now(timezone.utc)
    scientific = SignalState.model_validate_json((root / "state/signal-state.json").read_text())
    allowed = {item.evidence_id for item in scientific.evidence}
    ev = [eid for eid in ("ev-zhuang-2011-intranasal-exosome", "ev-kodali-2017-status-epilepticus",
                          "ev-hermann-2023-neonatal-hi", "ev-misev2023-quality-framework",
                          "ev-driedonks-2022-macaque-biodistribution") if eid in allowed]
    missing = StrategyConfidence.MISSING
    low = StrategyConfidence.LOW
    moderate = StrategyConfidence.MODERATE
    candidates = [
        _initial_candidate("sgl001-architecture-a", "SGL-001A", "Secretome-retaining MSC product",
            "MSC-derived cell-free product retaining EV and non-EV secretome components.", "biological cell-free mixture",
            "Current provisional lead for evaluation of a near-term legitimate development path.", ArchitectureDisposition.PROVISIONAL_LEAD,
            [3, 2, 2, 4, 2, 2, 2], [low, low, low, moderate, low, low, low], timestamp, ev,
            "Retains the broader paracrine system represented in the current program hypothesis.",
            "Product identity, potency, lot consistency and human-development gates remain unresolved.",
            ["Active contributors", "Reproducible product definition", "Legitimate human-study pathway"],
            "Define and compare a reproducible secretome-retaining product fingerprint."),
        _initial_candidate("sgl001-architecture-b", "SGL-001B", "EV-enriched MSC product",
            "MSC-derived preparation enriched for extracellular vesicles.", "EV-enriched biological product",
            "Refinement and comparator to the provisional lead.", ArchitectureDisposition.ACTIVE_COMPARATOR,
            [2, 2, 3, 4, 2, 2, 2], [low, low, moderate, moderate, low, low, low], timestamp, ev,
            "A narrower EV-enriched identity may improve analytical characterization.",
            "It is unknown whether enrichment retains the relevant multi-component activity.",
            ["EV versus non-EV contribution", "Recovery and purity tradeoffs", "Potency linkage"],
            "Run a matched EV-enriched versus secretome-retaining characterization comparison."),
        _initial_candidate("sgl001-architecture-c", "SGL-001C", "Defined RNA-LNP product",
            "Defined RNA cargo delivered with a lipid nanoparticle system.", "defined synthetic nucleic-acid product",
            "Defined synthetic comparator.", ArchitectureDisposition.ACTIVE_COMPARATOR,
            [1, 2, 4, 3, 3, 4, 3], [missing, low, low, low, low, low, low], timestamp, [],
            "Could provide a more defined cargo and scalable product concept if active biology is identified.",
            "No SGL-001 active RNA set or intranasal RNA-LNP package is established.",
            ["Active RNA identity", "Intranasal delivery", "Safety and tolerability"],
            "Identify whether a defined cargo set can reproduce a measurable product-relevant signal."),
        _initial_candidate("sgl001-architecture-d", "SGL-001D", "Engineered-EV product",
            "Engineered extracellular vesicles carrying selected biological cargo.", "engineered biological delivery product",
            "Longer-term engineered biological comparator.", ArchitectureDisposition.RESEARCH_ONLY,
            [1, 1, 3, 3, 1, 2, 2], [missing, missing, low, low, missing, low, low], timestamp, ev[:1],
            "May combine biological delivery with more deliberate cargo definition.",
            "Engineering, manufacturing, safety and active-cargo assumptions are unresolved.",
            ["Cargo selection", "Engineering reproducibility", "Comparative safety"],
            "Keep as a comparator until active cargo and product requirements are better defined."),
        _initial_candidate("sgl001-architecture-e", "SGL-001E", "Non-lipid nanoparticle candidate",
            "Non-lipid nanoparticle concept for a future defined cargo architecture.", "non-lipid nanoparticle",
            "Watchlist candidate.", ArchitectureDisposition.WATCHLIST,
            [0, 0, 1, 1, 0, 1, 0], [missing, missing, missing, missing, missing, missing, missing], timestamp, [],
            "Provides a future non-lipid delivery alternative for comparison.",
            "No canonical candidate, cargo, delivery, safety or manufacturing evidence is recorded.",
            ["Material selection", "Cargo compatibility", "Intranasal performance"],
            "Retain on watchlist pending a source-supported candidate concept."),
    ]
    ranking = [item.candidate_id for item in sorted(candidates, key=lambda x: (-x.confidence_adjusted_decision_score, x.candidate_id))]
    run_id = "strategy-seed-sgl001"
    determination = StrategyDetermination(
        determination_id="strategy-determination-seed-sgl001", run_id=run_id, program_id="SGL-001",
        determination=StrategyDeterminationType.HUMAN_DECISION_REQUIRED,
        recommended_candidate_id=ranking[0], prior_lead_candidate_id="sgl001-architecture-a",
        proposed_ranking=ranking,
        rationale="SGL-001A remains a provisional, human-gated lead; all architectures have unresolved hard gates and limited confidence.",
        adversary_summary="The ranking is sensitive to low-confidence assumptions and must not be interpreted as probability of success.",
        unresolved_gates=[gate.gate_id for item in candidates for gate in item.hard_gates], created_at=timestamp,
    )
    scores = {item.candidate_id: item.confidence_adjusted_decision_score for item in candidates}
    history = StrategyAssessmentHistoryEntry(
        history_entry_id="strategy-history-seed-sgl001", run_id=run_id, assessed_at=timestamp,
        prior_scores={}, new_scores=scores, prior_ranking=[], proposed_ranking=ranking,
        score_deltas=scores, changed_inputs=["Initial conservative strategy baseline from existing canonical state."],
        evidence_ids=ev, determination=determination.determination,
        human_approval_status=determination.approval_status,
    )
    return ProductStrategyWorkspace(
        therapeutic_objective=TherapeuticObjective(
            objective_id="therapeutic-objective-sgl001", program_id="SGL-001",
            statement="Evaluate a reproducibly characterized intranasal, cell-free regenerative product intended to support cognitive function and neuroregenerative biology.",
            intended_strategy="Compare alternative product architectures for the same intended therapeutic strategy without assuming established efficacy.",
            disclaimer="This objective is a development hypothesis, not evidence that SGL-001 is safe, effective, approved, or ready for human administration.",
            evidence_ids=ev,
        ), dimension_weights=DIMENSION_WEIGHTS, candidates=candidates,
        current_provisional_lead_candidate_id="sgl001-architecture-a",
        latest_determination=determination, assessment_history=[history],
        input_fingerprint=strategy_input_fingerprint(root), updated_at=timestamp,
    )


def validate_strategy_evidence(workspace: ProductStrategyWorkspace, allowed: set[str]) -> None:
    refs = set(workspace.therapeutic_objective.evidence_ids)
    for candidate in workspace.candidates:
        refs.update(candidate.evidence_ids)
        for item in candidate.dimension_assessments:
            refs.update(item.evidence_ids)
        for gate in candidate.hard_gates:
            refs.update(gate.evidence_ids)
    for entry in workspace.assessment_history:
        refs.update(entry.evidence_ids)
    if refs - allowed:
        raise ValueError(f"product strategy references unknown canonical evidence: {sorted(refs - allowed)}")


COUNCIL_PROMPT = """Assess only the assigned strategy dimension for all five supplied SGL-001 candidate architectures. Use only allowed evidence IDs. Preserve missing evidence as missing or low confidence. Do not claim efficacy, safety, approval, legal eligibility, completed experiments, or probability of success. Return the typed assessment."""
ADVERSARY_PROMPT = """Challenge unsupported ratings, false precision, hidden failed gates, evidence double-counting, incomparable assumptions, regulatory overconfidence, and unsupported recommendation changes. Return concise structured objections only."""
CHAIR_PROMPT = """Recommend a determination from the allowed enum. You may propose a lead but cannot approve or promote it. Any lead change requires human decision. Do not alter deterministic scores or invent evidence."""


class ProductStrategyOrchestrator:
    def __init__(self, *, client: ModelClient | None, root: Path, now_factory=lambda: datetime.now(timezone.utc)):
        self.client, self.root, self.now_factory = client, root, now_factory
        self.last_run_id: str | None = None

    def run(self, *, run_id: str | None = None) -> ProductStrategyWorkspace:
        active_id, now = run_id or new_run_id(), self.now_factory()
        self.last_run_id = active_id
        store = RunStore(self.root / "strategy-runs", active_id)
        path = self.root / "state/product-strategy.json"
        current = ProductStrategyWorkspace.model_validate_json(path.read_text()) if path.exists() else initial_product_strategy(self.root, now=now)
        fingerprint = strategy_input_fingerprint(self.root)
        if fingerprint == current.input_fingerprint:
            store.write_json("00-run-input.json", {"run_id": active_id, "input_fingerprint": fingerprint})
            store.write_json("01-no-material-change.json", {"determination": "no_material_change", "reason": "Canonical strategy inputs are unchanged."})
            store.write_json("99-run-complete.json", {"run_id": active_id, "state_changed": False})
            return current
        if self.client is None:
            raise RuntimeError("OPENAI_API_KEY is required when strategy inputs materially changed")
        scientific = SignalState.model_validate_json((self.root / "state/signal-state.json").read_text())
        allowed = {item.evidence_id for item in scientific.evidence}
        context = {"candidates": current.candidates, "objective": current.therapeutic_objective,
                   "allowed_evidence_ids": sorted(allowed), "hard_gates": GATE_NAMES}
        store.write_json("00-run-input.json", context)
        by_candidate: dict[str, list[ArchitectureDimensionAssessment]] = {item.candidate_id: [] for item in current.candidates}
        for index, dimension in enumerate(ArchitectureDimension, start=1):
            output = self.client.generate(
                instructions=f"{COUNCIL_PROMPT}\nRole: {SPECIALIST_ROLES[dimension]}",
                input_text=json.dumps(TypeAdapter(object).dump_python(context, mode="json")),
                output_type=StrategySpecialistAssessment,
            )
            if output.dimension is not dimension or {x.candidate_id for x in output.candidates} != set(by_candidate):
                raise ValueError("strategy specialist output does not cover the assigned dimension and candidates")
            if any(set(item.evidence_ids) - allowed for item in output.candidates):
                raise ValueError("strategy specialist references unknown canonical evidence")
            store.write_json(f"{index:02d}-{dimension.value}.json", output)
            for item in output.candidates:
                by_candidate[item.candidate_id].append(score_dimension(
                    candidate_id=item.candidate_id, dimension=dimension, rating=item.rating,
                    confidence=item.confidence, evidence_status=item.evidence_status,
                    rationale=item.rationale, uncertainty=item.uncertainty,
                    evidence_ids=item.evidence_ids, source_type=item.source_type,
                    assessment_id=f"assessment-{active_id}-{item.candidate_id}-{dimension.value}",
                ))
        updated_candidates = [score_candidate(item, by_candidate[item.candidate_id], assessed_at=now) for item in current.candidates]
        ranking = [item.candidate_id for item in sorted(updated_candidates, key=lambda x: (-x.confidence_adjusted_decision_score, x.candidate_id))]
        adversary = self.client.generate(instructions=ADVERSARY_PROMPT,
            input_text=json.dumps({"candidates": [x.model_dump(mode="json") for x in updated_candidates], "ranking": ranking}),
            output_type=StrategyAdversaryReview)
        chair = self.client.generate(instructions=CHAIR_PROMPT,
            input_text=json.dumps({"ranking": ranking, "adversary": adversary.model_dump(mode="json")}),
            output_type=StrategyChairRecommendation)
        if set(chair.evidence_ids) - allowed or chair.recommended_candidate_id not in set(ranking):
            raise ValueError("strategy chair references unknown canonical state")
        determination_type = chair.determination
        if chair.recommended_candidate_id != current.current_provisional_lead_candidate_id:
            determination_type = StrategyDeterminationType.HUMAN_DECISION_REQUIRED
        determination = StrategyDetermination(
            determination_id=f"strategy-determination-{active_id}", run_id=active_id, program_id="SGL-001",
            determination=determination_type, recommended_candidate_id=chair.recommended_candidate_id,
            prior_lead_candidate_id=current.current_provisional_lead_candidate_id,
            proposed_ranking=ranking, rationale=chair.rationale,
            adversary_summary=adversary.strongest_objection,
            unresolved_gates=[g.gate_id for c in updated_candidates for g in c.hard_gates if g.status is not HardGateState.PASSED],
            created_at=now,
        )
        prior_scores = {item.candidate_id: item.confidence_adjusted_decision_score for item in current.candidates}
        new_scores = {item.candidate_id: item.confidence_adjusted_decision_score for item in updated_candidates}
        prior_ranking = current.latest_determination.proposed_ranking
        history = StrategyAssessmentHistoryEntry(
            history_entry_id=f"strategy-history-{active_id}", run_id=active_id, assessed_at=now,
            prior_scores=prior_scores, new_scores=new_scores, prior_ranking=prior_ranking,
            proposed_ranking=ranking, score_deltas={key: new_scores[key] - prior_scores[key] for key in new_scores},
            changed_inputs=chair.changed_inputs, evidence_ids=chair.evidence_ids,
            determination=determination_type, human_approval_status=determination.approval_status,
        )
        updated = current.model_copy(update={"candidates": updated_candidates,
            "latest_determination": determination, "assessment_history": [*current.assessment_history, history],
            "input_fingerprint": fingerprint, "updated_at": now})
        updated = ProductStrategyWorkspace.model_validate(updated.model_dump(mode="python"))
        validate_strategy_evidence(updated, allowed)
        from signalai.publisher import build_current_public_state
        public = build_current_public_state(self.root, generated_at=now, strategy_workspace=updated)
        type(public).model_validate(public.model_dump(mode="python", by_alias=True))
        store.write_json("08-adversary.json", adversary)
        store.write_json("09-chair.json", determination)
        store.write_json("10-workspace.json", updated)
        publish_json(path, updated)
        publish_json(self.root / "public/signal-state.json", public)
        store.write_json("99-run-complete.json", {"run_id": active_id, "state_changed": True})
        return updated
