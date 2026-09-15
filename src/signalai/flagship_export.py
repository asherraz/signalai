"""Deterministic synthesis of canonical state and SignalRB; no model call."""

import re

from signalai.schemas.models import SignalState
from signalai.schemas.signalrb import PublicSignalRB
from signalai.schemas.public_flagship import (
    FlagshipSourceRefs, PublicDevelopmentGate, PublicFlagshipProgram,
    PublicFlagshipThesis, PublicPivotCriterion, PublicProgramHistoryEntry,
)


# This registry defines presentation categories, not progress or scientific findings.
GATE_CATEGORIES = (
    ("product-definition", "Product Definition", ("product definition", "candidate", "source-cell", "source cell", "production")),
    ("potency-identity", "Potency / Identity", ("potency", "identity", "analytics", "analytical", "qc")),
    ("intranasal-delivery", "Intranasal Delivery", ("intranasal", "cross-species", "biodistribution")),
    ("mechanism-biology", "Mechanism / Active Biology", ("cargo", "mechanism", "active biology")),
    ("chassis-decision", "Chassis Decision", ("chassis", "synthetic delivery", "carrier selection")),
    ("translational-readiness", "Translational Readiness", ("generalizability", "cognition", "aging", "jurisdiction", "clinic", "translational")),
)


def concise(text: str | None, limit: int = 220) -> str | None:
    if not text:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    # Prefer a complete sourced sentence; never cut a qualifier or action in half.
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized, maxsplit=1)[0]
    return first if len(first) <= limit else normalized


def _matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text.casefold() for term in terms)


def export_flagship_program(state: SignalState, board: PublicSignalRB | None) -> PublicFlagshipProgram:
    program = state.program
    allowed_evidence = {e.evidence_id for e in state.evidence}
    reviews = {r.run_id: r for r in board.recent_reviews if r.program_id == program.program_id} if board else {}
    if board and board.latest_review and board.latest_review.program_id == program.program_id:
        reviews[board.latest_review.run_id] = board.latest_review
    ordered = sorted(reviews.values(), key=lambda r: (r.created_at, r.run_id))
    latest = ordered[-1] if ordered else None
    if any(set(r.evidence_ids) - allowed_evidence for r in ordered):
        raise ValueError("flagship review references unknown canonical evidence")
    open_risks = [r for r in state.risks if r.status.value == "open"]
    gates = []
    for key, name, terms in GATE_CATEGORIES:
        risks = [r for r in open_risks if _matches(r.title + " " + r.description, terms)]
        claims = [c for c in state.claims if _matches(c.statement, terms)]
        linked_reviews = [r for r in ordered if _matches(r.matter_title + " " + r.matter_question, terms)]
        known = [concise(c.statement) for c in claims if c.status.value == "supported"][:1]
        missing = [concise(r.description) for r in risks]
        missing += [concise(c.statement) for c in claims if c.status.value != "supported"]
        fields = []
        status = "unresolved"
        if key == "product-definition" and program.current_formulation_hypothesis:
            known.insert(0, concise(program.current_formulation_hypothesis))
            fields.append("current_formulation_hypothesis")
            status = "partially_defined"
        if key == "mechanism-biology" and program.current_formulation_hypothesis:
            missing.append(concise(program.current_formulation_hypothesis))
            fields.append("current_formulation_hypothesis")
        if key != "product-definition" and any(r.severity.value in {"high", "critical"} for r in risks):
            status = "blocked"
        if latest and latest in linked_reviews and latest.human_decision_required:
            status = "human_decision"
        # Cited preclinical literature does not establish completion of an asset gate.
        if not missing:
            missing = ["Gate completion is not recorded in the supplied canonical program state or SignalRB reviews."]
        next_action = concise(risks[0].mitigation) if risks else None
        if latest and latest in linked_reviews:
            next_action = concise(latest.next_action)
        elif not next_action and linked_reviews:
            next_action = concise(linked_reviews[-1].next_action)
        evidence = list(dict.fromkeys([e for c in claims for e in c.evidence_ids] + [e for r in risks for e in r.evidence_ids] + [e for r in linked_reviews for e in r.evidence_ids]))
        gates.append(PublicDevelopmentGate(
            gate_id=f"{program.program_id.lower()}-{key}", name=name, status=status,
            why_it_matters=concise(risks[0].description) if risks else (
                concise(linked_reviews[-1].matter_question) if linked_reviews else "No canonical assessment recorded for this gate."
            ), what_is_known=list(dict.fromkeys(known)), what_is_missing=list(dict.fromkeys(missing)),
            next_action=next_action, sources=FlagshipSourceRefs(
                claim_ids=[c.claim_id for c in claims], evidence_ids=evidence,
                risk_ids=[r.risk_id for r in risks], review_ids=[r.review_id for r in linked_reviews], program_fields=fields,
            ),
        ))
    pivots = []
    seen_conditions = set()
    for review in ordered:
        for index, condition in enumerate(review.conditions):
            # Retain only explicit disconfirmation, not every procedural requirement.
            if not re.search(r"\b(fails?|weaken\w*)\b", condition, re.IGNORECASE):
                continue
            normalized = " ".join(condition.split()).casefold()
            if normalized in seen_conditions:
                continue
            seen_conditions.add(normalized)
            pivots.append(PublicPivotCriterion(
                criterion_id=f"{review.review_id}-condition-{index}", condition=condition,
                review_id=review.review_id, evidence_ids=review.evidence_ids,
            ))
    history = [PublicProgramHistoryEntry(
        date=r.created_at, matter_title=r.matter_title, determination_type=r.determination_type,
        state_change=("Scientific state changed. " if r.state_change is True else "Scientific state change not recorded. " if r.state_change == "not_recorded" else "No scientific state change. ") + ("Pending recommendation: " if r.human_decision_required else "Recorded determination: ") + (concise(r.determination.split(": ", 1)[0]) or "not_recorded"),
        review_id=r.review_id, run_id=r.run_id,
    ) for r in ordered]
    biology_claim = next((c for c in state.claims if c.status.value == "supported" and "msc-derived" in c.statement.casefold()), None)
    product_review = next((r for r in reversed(ordered) if "product definition" in r.matter_title.casefold()), None)
    thesis_sources = FlagshipSourceRefs(
        claim_ids=[biology_claim.claim_id] if biology_claim else [],
        evidence_ids=biology_claim.evidence_ids if biology_claim else [],
        hypothesis_ids=[state.hypothesis.hypothesis_id],
        review_ids=[product_review.review_id] if product_review else [],
        program_fields=["current_formulation_hypothesis", "route_of_administration", "development_focus"],
    )
    result = PublicFlagshipProgram(
        programId=program.program_id, name=program.asset_name, displayName=program.asset_name,
        subtitle=f"Flagship therapeutic program of Signal Intelligence · {program.development_focus or program.modality}",
        oneLineThesis=("Product hypothesis: " + (concise(program.current_formulation_hypothesis) or program.modality)),
        thesis=PublicFlagshipThesis(
            biology=concise(biology_claim.statement) if biology_claim else None,
            product_hypothesis=concise(program.current_formulation_hypothesis), route=program.route_of_administration,
            development_hypothesis=concise(state.hypothesis.statement), sources=thesis_sources,
            development_question=concise(product_review.matter_question) if product_review else None,
        ), status=program.status.value,
        currentDetermination=concise(latest.determination) if latest else None,
        strongestCaseFor=concise(latest.strongest_case_for) if latest else None,
        strongestCaseAgainst=concise(latest.strongest_case_against) if latest else None,
        humanDecisionRequired=latest.human_decision_required if latest else state.decision.requires_human_approval,
        verificationStatus=latest.verification_status if latest else None,
        currentBlockers=[r.title for r in open_risks], developmentGates=gates,
        currentNextAction=concise(latest.next_action if latest else program.next_proposed_action),
        pivotCriteria=pivots, signalRBReviewId=latest.review_id if latest else None,
        evidenceConfidence=program.evidence_confidence.value if program.evidence_confidence else None,
        updatedAt=max([program.updated_at] + [r.created_at for r in ordered]), programHistory=history,
        sources=FlagshipSourceRefs(
            evidence_ids=list(dict.fromkeys(state.hypothesis.evidence_ids + [e for g in gates for e in g.sources.evidence_ids])),
            claim_ids=program.claim_ids, risk_ids=[r.risk_id for r in open_risks], hypothesis_ids=program.hypothesis_ids,
            review_ids=[r.review_id for r in ordered], program_fields=["status", "evidence_confidence", "next_proposed_action"],
        ),
    )
    if set(result.sources.evidence_ids) - allowed_evidence:
        raise ValueError("flagship references unknown canonical evidence")
    return result
