"""Read-only, audited migration of legacy SignalAgent JSON into SignalAI state."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signalai.schemas import (
    ActionStatus,
    BiologicalPathway,
    CargoCandidate,
    CargoPathwayLink,
    CargoState,
    CargoType,
    DevelopmentAction,
    DevelopmentAgenda,
    DevelopmentDisposition,
    EnforcementAction,
    EnforcementIntensity,
    EvidenceLevel,
    ExcipientCandidate,
    FormulationCandidate,
    FormulationScore,
    FormulationState,
    Jurisdiction,
    JurisdictionLegalBasis,
    JurisdictionSourceDocument,
    JurisdictionState,
    JurisdictionVerificationStatus,
    JurisdictionVerdict,
    LegacyMigrationReport,
    MigrationSourceSummary,
    PresentationCandidate,
    PriorityLevel,
    ScoreLevel,
    SignalState,
    TherapeuticAssetWorkspace,
)
from signalai.storage import publish_json
from signalai.workspace_export import validate_workspace_references


LEGACY_CARGO_FIELDS = {
    "id", "tier", "sources", "targets", "pathway", "effect", "tissues",
    "evidence", "caveat", "contextDependent", "keyCitation",
}
LEGACY_ACTIVE_FIELDS = {
    "name", "class", "mechanism_score", "evidence_score",
    "manufacturability_score", "regulatory_score", "status", "note",
}
LEGACY_EXCIPIENT_FIELDS = {
    "name", "function", "precedent", "tradeoff", "precedent_strength",
    "ev_stability", "status",
}
LEGACY_PRESENTATION_FIELDS = {"format", "shelf_life", "cold_chain", "user_steps", "verdict"}
LEGACY_JURISDICTION_FIELDS = {
    "id", "name", "region", "verdict", "classification", "legal_basis",
    "permitted", "grey", "prohibited", "cell_sources", "enforcement",
    "route_in", "last_verified", "confidence", "open_questions", "priority",
    "frontier", "headline", "momentum", "tension", "through_line", "sources",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


def _unmapped(records: list[dict[str, Any]], known: set[str]) -> list[str]:
    return sorted(set().union(*(record.keys() for record in records)) - known)


def _cargo_level(value: str) -> EvidenceLevel:
    return EvidenceLevel.MODERATE if value == "animal+invitro" else EvidenceLevel.LOW


def _score_level(value: int) -> ScoreLevel:
    if value <= 0:
        return ScoreLevel.NOT_ASSESSED
    if value <= 2:
        return ScoreLevel.LOW
    if value <= 4:
        return ScoreLevel.MODERATE
    return ScoreLevel.HIGH


def _compatibility_level(value: int) -> ScoreLevel:
    return {0: ScoreLevel.LOW, 1: ScoreLevel.LOW, 2: ScoreLevel.MODERATE}.get(
        value, ScoreLevel.HIGH
    )


def _disposition(value: str) -> DevelopmentDisposition:
    return {
        "focus": DevelopmentDisposition.FOCUS,
        "benchmark": DevelopmentDisposition.BENCHMARK,
        "excluded": DevelopmentDisposition.EXCLUDED,
        "chosen": DevelopmentDisposition.FOCUS,
        "candidate": DevelopmentDisposition.CANDIDATE,
        "ruled-out": DevelopmentDisposition.EXCLUDED,
    }[value]


def _priority(value: int | None) -> PriorityLevel:
    if value is None:
        return PriorityLevel.NOT_ASSESSED
    if value <= 3:
        return PriorityLevel.CRITICAL
    if value <= 6:
        return PriorityLevel.HIGH
    if value <= 9:
        return PriorityLevel.MODERATE
    return PriorityLevel.LOW


def _confidence(value: str) -> EvidenceLevel:
    return {
        "low": EvidenceLevel.LOW,
        "medium": EvidenceLevel.MODERATE,
        "high": EvidenceLevel.HIGH,
    }[value]


def _verdict(value: str) -> JurisdictionVerdict:
    return {
        "legal": JurisdictionVerdict.VIABLE,
        "grey": JurisdictionVerdict.GREY,
        "restrictive": JurisdictionVerdict.RESTRICTIVE,
        "illegal": JurisdictionVerdict.PROHIBITED,
        "prohibited": JurisdictionVerdict.PROHIBITED,
        "unresolved": JurisdictionVerdict.UNRESOLVED,
    }[value]


def _country(record: dict[str, Any]) -> str:
    return {
        "jp": "Japan", "kr": "South Korea", "cn": "China", "th": "Thailand",
        "ae": "United Arab Emirates", "de": "Germany", "ch": "Switzerland",
        "us": "United States", "us-fl": "United States", "pa": "Panama",
        "co": "Colombia", "mx": "Mexico",
    }.get(record["id"], record["name"])


def migrate_legacy_workspace(
    *,
    cargo_path: Path,
    formulation_path: Path,
    jurisdictions_path: Path,
    seed_workspace: TherapeuticAssetWorkspace,
    scientific_state: SignalState,
    agenda: DevelopmentAgenda,
    generated_at: datetime | None = None,
) -> tuple[TherapeuticAssetWorkspace, LegacyMigrationReport]:
    now = generated_at or datetime.now(timezone.utc)
    cargo_rows: list[dict[str, Any]] = _load(cargo_path)
    formulation_data: dict[str, list[dict[str, Any]]] = _load(formulation_path)
    jurisdiction_rows: list[dict[str, Any]] = _load(jurisdictions_path)["jurisdictions"]

    seed_candidates = [
        item for item in seed_workspace.cargo.candidates if item.cargo_type is not CargoType.MIRNA
    ]
    seed_pathways = {
        item.pathway_id: item
        for item in seed_workspace.cargo.pathways
        if not item.pathway_id.startswith("pathway-legacy-")
    }
    seed_pathway_links = [
        item
        for item in seed_workspace.cargo.pathway_links
        if not item.cargo_candidate_id.startswith("cargo-mirna-")
    ]
    imported_pathways: dict[str, BiologicalPathway] = {}
    imported_cargo: list[CargoCandidate] = []
    imported_pathway_links: list[CargoPathwayLink] = []
    for row in cargo_rows:
        pathway_id = f"pathway-legacy-{_slug(row['pathway'])}"
        imported_pathways.setdefault(
            pathway_id,
            BiologicalPathway(
                pathway_id=pathway_id,
                name=row["pathway"],
                description="Pathway assignment reported by the legacy cargo dataset; requires source-level verification before decision use.",
                evidence_ids=[],
            ),
        )
        candidate_id = f"cargo-mirna-{_slug(row['id'])}"
        imported_cargo.append(
            CargoCandidate(
                cargo_candidate_id=candidate_id,
                name=row["id"],
                cargo_type=CargoType.MIRNA,
                source=", ".join(row["sources"]),
                mechanism=row["effect"],
                target_pathway_ids=[pathway_id],
                relevant_tissues=row["tissues"],
                evidence_ids=[],
                evidence_level=_cargo_level(row["evidence"]),
                supportive_evidence_ids=[],
                contradictory_evidence_ids=[],
                rationale=f"Imported biological-design candidate from legacy tier '{row['tier']}'.",
                development_status=DevelopmentDisposition.CANDIDATE,
                evidence_rank=None,
                uncertainty=row["caveat"],
                biological_targets=row["targets"],
                evidence_annotation=row["evidence"],
                source_citation=row["keyCitation"],
                context_dependent=row["contextDependent"],
                legacy_source_file=str(cargo_path),
            )
        )
        imported_pathway_links.append(
            CargoPathwayLink(
                cargo_candidate_id=candidate_id,
                pathway_id=pathway_id,
                evidence_ids=[],
                rationale="Legacy dataset pathway mapping; citation retained on the candidate and not promoted into canonical evidence.",
            )
        )
    cargo = CargoState(
        operator_focus_candidate_ids=seed_workspace.cargo.operator_focus_candidate_ids,
        ranking_methodology=seed_workspace.cargo.ranking_methodology,
        candidates=seed_candidates + imported_cargo,
        pathways=list(seed_pathways.values()) + list(imported_pathways.values()),
        evidence_links=seed_workspace.cargo.evidence_links,
        pathway_links=seed_pathway_links + imported_pathway_links,
        links=seed_workspace.cargo.links,
    )

    active_rows = formulation_data["actives"]
    formulation_candidates: list[FormulationCandidate] = []
    for row in active_rows:
        levels = [_score_level(row[key]) for key in (
            "mechanism_score", "evidence_score", "manufacturability_score", "regulatory_score"
        )]
        status = _disposition(row["status"])
        formulation_candidates.append(
            FormulationCandidate(
                formulation_candidate_id=f"formulation-legacy-{_slug(row['name'])}",
                name=row["name"],
                modality=row["class"],
                active_cargo_strategy=row["name"],
                route="intranasal",
                score=FormulationScore(
                    mechanism=levels[0], evidence=levels[1], manufacturability=levels[2],
                    regulatory_deployment=levels[3],
                    total_score=sum({ScoreLevel.NOT_ASSESSED: 0, ScoreLevel.LOW: 1, ScoreLevel.MODERATE: 2, ScoreLevel.HIGH: 3}[x] for x in levels),
                    methodology="Legacy 0–5 scores normalized to SignalAI ordinal bands; exact source scores retained in legacy_scores.",
                ),
                status=status,
                rationale=row["note"],
                tradeoffs=[row["note"]],
                evidence_ids=[],
                exclusion_reason=row["note"] if status is DevelopmentDisposition.EXCLUDED else None,
                legacy_scores={key: row[key] for key in (
                    "mechanism_score", "evidence_score", "manufacturability_score", "regulatory_score"
                )},
                legacy_source_file=str(formulation_path),
            )
        )
    excipients: list[ExcipientCandidate] = []
    for row in formulation_data["excipients"]:
        status = _disposition(row["status"])
        concentration = None
        match = re.search(r"\(([^)]+)\)$", row["name"])
        if match:
            concentration = match.group(1)
        excipients.append(
            ExcipientCandidate(
                excipient_candidate_id=f"excipient-legacy-{_slug(row['name'])}",
                name=row["name"],
                functional_role=row["function"],
                proposed_concentration=concentration,
                ev_compatibility=_compatibility_level(row["ev_stability"]),
                intranasal_precedent=_compatibility_level(row["precedent_strength"]),
                human_precedent=_compatibility_level(row["precedent_strength"]),
                regulatory_precedent=_compatibility_level(row["precedent_strength"]),
                formulation_value=ScoreLevel.NOT_ASSESSED,
                risk=row["tradeoff"],
                evidence_ids=[],
                inclusion_status=status,
                exclusion_reason=row["tradeoff"] if status is DevelopmentDisposition.EXCLUDED else None,
                precedent_summary=row["precedent"],
                tradeoff=row["tradeoff"],
                legacy_precedent_strength=row["precedent_strength"],
                legacy_ev_stability=row["ev_stability"],
                legacy_source_file=str(formulation_path),
            )
        )
    presentations = [
        PresentationCandidate(
            presentation_id=f"presentation-legacy-{_slug(row['format'])}",
            format=row["format"], shelf_life=row["shelf_life"], cold_chain=row["cold_chain"],
            user_steps=row["user_steps"], verdict=row["verdict"],
            status=(DevelopmentDisposition.EXCLUDED if row["verdict"].lower().startswith("ruled out") else DevelopmentDisposition.CANDIDATE),
            legacy_source_file=str(formulation_path),
        )
        for row in formulation_data["presentation"]
    ]
    formulation = FormulationState(
        scoring_methodology="Legacy 0–5 component scores are preserved exactly in legacy_scores and normalized into uncalibrated SignalAI ordinal bands for comparison; totals are not probabilities or validated product scores.",
        candidates=formulation_candidates,
        excipients=excipients,
        attributes=seed_workspace.formulation.attributes,
        presentations=presentations,
        links=seed_workspace.formulation.links,
    )

    source_documents: list[JurisdictionSourceDocument] = []
    jurisdictions: list[Jurisdiction] = []
    for row in jurisdiction_rows:
        jurisdiction_source_ids: list[str] = []
        legal_basis = []
        for index, basis in enumerate(row["legal_basis"], start=1):
            source_id = f"source-legacy-{_slug(row['id'])}-legal-{index}"
            jurisdiction_source_ids.append(source_id)
            source_documents.append(
                JurisdictionSourceDocument(
                    source_document_id=source_id,
                    title=basis["instrument"],
                    issuer=f"Legacy citation for {row['name']}",
                    source_uri=None,
                    published_at=None,
                    accessed_at=now,
                    locator=basis["summary"],
                    citation=basis["citation"],
                    legacy_source_file=str(jurisdictions_path),
                )
            )
            legal_basis.append(
                JurisdictionLegalBasis(
                    instrument=basis["instrument"],
                    citation=basis["citation"] or None,
                    date=basis["date"] or None,
                    summary=basis["summary"],
                )
            )
        for index, source in enumerate(row.get("sources", []), start=1):
            source_id = f"source-legacy-{_slug(row['id'])}-url-{index}"
            jurisdiction_source_ids.append(source_id)
            source_documents.append(
                JurisdictionSourceDocument(
                    source_document_id=source_id,
                    title=source["label"],
                    issuer=f"Linked source for {row['name']}",
                    source_uri=source["url"],
                    accessed_at=now,
                    citation=source["label"],
                    legacy_source_file=str(jurisdictions_path),
                )
            )
        classification = row["classification"]
        enforcement = row["enforcement"]
        next_action = DevelopmentAction(
            action_id=f"action-verify-jurisdiction-{_slug(row['id'])}",
            action=f"Verify the legacy {row['name']} market-entry assessment against current primary sources and qualified local counsel.",
            objective="Determine whether a legitimate SGL-001 product-development and clinic pathway exists.",
            rationale="The imported verdict is traceable but has not been independently revalidated by this migration.",
            uncertainty="Current product classification, human-use authorization, manufacturing/import, sourcing, and advertising requirements.",
            success_criteria=["A dated, source-linked assessment distinguishes legal authorization from enforcement intensity."],
            status=ActionStatus.PROPOSED,
            requires_human_approval=True,
            linked_hypothesis_ids=[scientific_state.hypothesis.hypothesis_id],
            linked_risk_ids=[risk.risk_id for risk in scientific_state.risks],
            linked_decision_ids=[scientific_state.decision.decision_id],
            linked_agenda_item_ids=["agenda-jurisdiction-entry-path"],
        )
        jurisdictions.append(
            Jurisdiction(
                jurisdiction_id=f"jurisdiction-legacy-{_slug(row['id'])}",
                jurisdiction=row["name"], country=_country(row), region=row["region"],
                verdict=_verdict(row["verdict"]),
                enforcement_intensity=EnforcementIntensity(enforcement["level"]),
                evidence_confidence=_confidence(row["confidence"]),
                priority=_priority(row.get("priority")),
                product_classification=classification["product_status"],
                applicable_legal_framework=[f"{x['instrument']} — {x['citation']}: {x['summary']}" for x in row["legal_basis"]],
                private_clinic_path=f"{classification['clinical_status']} Route note: {row['route_in']}",
                physician_use_path=classification["clinical_status"],
                manufacturing_import_considerations=f"Legacy route note: {row['route_in']}. Product-specific manufacturing and import requirements require verification.",
                cell_tissue_sourcing_rules=json.dumps(row["cell_sources"], sort_keys=True),
                advertising_constraints="; ".join(row["prohibited"]),
                source_document_ids=jurisdiction_source_ids,
                last_verified_at=datetime.fromisoformat(row["last_verified"]).replace(tzinfo=timezone.utc),
                unresolved_questions=row["open_questions"], next_action=next_action,
                concise_rationale=row.get("through_line") or row.get("headline") or row["route_in"],
                verification_status=JurisdictionVerificationStatus.LEGACY_IMPORT_UNVERIFIED,
                clinical_status=classification["clinical_status"],
                cosmetic_status=classification["cosmetic_status"],
                permitted_activities=row["permitted"], grey_areas=row["grey"],
                prohibited_activities=row["prohibited"], cell_source_rules=row["cell_sources"],
                enforcement_actions=[EnforcementAction(**item) for item in enforcement["recent_actions"]],
                legacy_priority_rank=row.get("priority"), frontier=row.get("frontier", False),
                headline=row.get("headline"), momentum=row.get("momentum"),
                tension=row.get("tension"), through_line=row.get("through_line"),
                legacy_source_file=str(jurisdictions_path), legal_basis=legal_basis,
            )
        )
    jurisdiction_state = JurisdictionState(
        disclaimer="Imported legacy planning data, not legal advice. Reported verdicts and confidence are preserved for traceability but marked legacy_import_unverified; verify current primary law and obtain qualified local advice before action.",
        sources=source_documents,
        jurisdictions=jurisdictions,
        links=seed_workspace.jurisdictions.links,
    )

    workspace = TherapeuticAssetWorkspace(
        schema_version="1.1",
        program_id=scientific_state.program.program_id,
        generated_at=now,
        cargo=cargo,
        formulation=formulation,
        jurisdictions=jurisdiction_state,
    )
    validate_workspace_references(workspace, scientific_state, agenda)

    report = LegacyMigrationReport(
        migration_id=f"legacy-import-{now.strftime('%Y%m%dT%H%M%SZ')}",
        generated_at=now,
        sources=[
            MigrationSourceSummary(
                source_file=str(cargo_path), source_sha256=_sha256(cargo_path),
                source_record_counts={"cargo_candidates": len(cargo_rows)},
                imported_record_counts={"cargo_candidates": len(imported_cargo), "pathways": len(imported_pathways), "pathway_links": len(imported_pathway_links)},
                mapped_fields=sorted(LEGACY_CARGO_FIELDS), unmapped_fields=_unmapped(cargo_rows, LEGACY_CARGO_FIELDS),
                mapping_notes=["Unverified keyCitation text is retained as source_citation and is not promoted into canonical Evidence.", "Legacy cargo records lacked development status; imported records are candidates while existing operator focus and benchmarks are preserved."],
            ),
            MigrationSourceSummary(
                source_file=str(formulation_path), source_sha256=_sha256(formulation_path),
                source_record_counts={key: len(value) for key, value in formulation_data.items()},
                imported_record_counts={"formulation_candidates": len(formulation_candidates), "excipients": len(excipients), "presentations": len(presentations)},
                mapped_fields=sorted(LEGACY_ACTIVE_FIELDS | LEGACY_EXCIPIENT_FIELDS | LEGACY_PRESENTATION_FIELDS),
                unmapped_fields=sorted(
                    set(_unmapped(active_rows, LEGACY_ACTIVE_FIELDS))
                    | set(_unmapped(formulation_data["excipients"], LEGACY_EXCIPIENT_FIELDS))
                    | set(_unmapped(formulation_data["presentation"], LEGACY_PRESENTATION_FIELDS))
                ),
                mapping_notes=["Original 0–5 scores are retained exactly; normalized ordinal bands are explicitly uncalibrated.", "Concentrations are extracted only when present parenthetically in the legacy name."],
            ),
            MigrationSourceSummary(
                source_file=str(jurisdictions_path), source_sha256=_sha256(jurisdictions_path),
                source_record_counts={"jurisdictions": len(jurisdiction_rows), "legal_basis": sum(len(x["legal_basis"]) for x in jurisdiction_rows), "linked_sources": sum(len(x.get("sources", [])) for x in jurisdiction_rows)},
                imported_record_counts={"jurisdictions": len(jurisdictions), "source_documents": len(source_documents)},
                mapped_fields=sorted(LEGACY_JURISDICTION_FIELDS), unmapped_fields=_unmapped(jurisdiction_rows, LEGACY_JURISDICTION_FIELDS),
                mapping_notes=["Legacy legal/illegal verdicts map to viable/prohibited; numeric priority is retained and also mapped into ordinal bands.", "All imported verdicts are marked legacy_import_unverified regardless of legacy confidence.", "Legal-basis citations without URLs remain traceable citation records but require primary-source verification."],
            ),
        ],
    )
    return workspace, report


def write_migration_outputs(
    *, workspace: TherapeuticAssetWorkspace, report: LegacyMigrationReport,
    workspace_path: Path, report_path: Path,
) -> None:
    publish_json(workspace_path, workspace)
    publish_json(report_path, report)
