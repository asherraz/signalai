"""Bounded discovery and public projection for the SGL-001 Molecular Atlas."""

from __future__ import annotations

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from signalai.schemas.molecular_atlas import (
    AtlasAccessLevel, AtlasContributionField, AtlasCoverage, AtlasCoverageItem, AtlasLayer,
    AtlasReviewPackage,
    AtlasReviewStatus, AtlasSourceKind, MolecularAtlasSource,
    MolecularAtlasWorkspace, PublicAtlasDiscovery, PublicMolecularAtlas,
)
from signalai.storage import publish_json
from signalai.storage import RunStore, new_run_id
from signalai.schemas.models import Evidence, EvidenceKind, SignalState


DEFAULT_QUERIES = [
    "mesenchymal stromal cell extracellular vesicle surface proteomics",
    "mesenchymal stromal cell secretome extracellular vesicle miRNA cargo",
    "extracellular vesicle glycomics surface lipidomics targeting",
    "MSC secretome proteomics potency assay manufacturing",
]


def initial_molecular_atlas(*, now: datetime | None = None) -> MolecularAtlasWorkspace:
    timestamp = now or datetime.now(timezone.utc)
    gaps = {
        AtlasLayer.CELL_SOURCE: (AtlasCoverage.LOW, "Link donor and source-cell state to reproducible product attributes."),
        AtlasLayer.MANUFACTURING_PROCESS: (AtlasCoverage.LOW, "Connect process variables to lot composition and potency."),
        AtlasLayer.SURFACE_CHEMISTRY: (AtlasCoverage.LOW, "Resolve proteins, glycans, lipids, and targeting relevance across lots."),
        AtlasLayer.RNA_CARGO: (AtlasCoverage.MODERATE, "Separate measured cargo from causal and functional cargo."),
        AtlasLayer.PROTEIN_CARGO: (AtlasCoverage.MODERATE, "Establish orthogonal quantification and lot reproducibility."),
        AtlasLayer.LIPID_AND_METABOLITE_CARGO: (AtlasCoverage.LOW, "Define composition, stability, and biological relevance."),
        AtlasLayer.SOLUBLE_SECRETOME: (AtlasCoverage.LOW, "Distinguish vesicular from non-vesicular contributions."),
        AtlasLayer.FUNCTIONAL_POTENCY: (AtlasCoverage.LOW, "Validate assays linking composition to a relevant biological response."),
        AtlasLayer.PRODUCT_SIGNATURE: (AtlasCoverage.NONE, "Define a human-approved, evidence-linked identity and potency signature."),
    }
    return MolecularAtlasWorkspace(
        coverage=[AtlasCoverageItem(
            layer=layer, label=layer.value.replace("_", " ").title(),
            coverage=gaps[layer][0], main_gap=gaps[layer][1],
        ) for layer in AtlasLayer],
        search_queries=DEFAULT_QUERIES, updated_at=timestamp,
    )


def _get_json(url: str, timeout: int = 30) -> dict:
    request = Request(url, headers={"User-Agent": "SignalAI/0.1 molecular-atlas discovery"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed trusted endpoints
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": "SignalAI/0.1 molecular-atlas processing"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed trusted endpoints
        return response.read().decode("utf-8", errors="replace")


def _source_id(source: str, record_id: str) -> str:
    digest = hashlib.sha256(f"{source}:{record_id}".encode()).hexdigest()[:16]
    return f"atlas-source-{digest}"


def discover_europe_pmc(query: str, *, limit: int, now: datetime, getter: Callable[[str], dict] = _get_json) -> list[MolecularAtlasSource]:
    start = (now - timedelta(days=30)).date().isoformat()
    end = now.date().isoformat()
    rolling_query = f"({query}) AND FIRST_PDATE:[{start} TO {end}]"
    params = urlencode({"query": rolling_query, "format": "json", "pageSize": limit, "sort": "FIRST_PDATE_D desc"})
    payload = getter(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}")
    records = []
    for item in payload.get("resultList", {}).get("result", []):
        record_id = str(item.get("pmid") or item.get("pmcid") or item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not record_id or not title:
            continue
        records.append(MolecularAtlasSource(
            source_id=_source_id("europe-pmc", record_id), source_name="Europe PMC",
            source_kind=AtlasSourceKind.PAPER, record_id=record_id, title=title,
            source_url=f"https://europepmc.org/article/MED/{record_id}",
            publication_date=str(item.get("firstPublicationDate") or item.get("pubYear") or "") or None,
            authors=[str(item.get("authorString"))] if item.get("authorString") else [],
            layers=infer_layers(f"{title} {item.get('journalTitle', '')}"), search_query=query,
            discovered_at=now, review_status=AtlasReviewStatus.TRIAGE_REQUIRED,
            provenance_note="Discovered from Europe PMC metadata; the full text and underlying data have not been reviewed.",
            data_use_note="Metadata-only discovery. Any full-text or dataset use remains subject to its license and repository terms.",
        ))
    return records


def discover_omicsdi(query: str, *, limit: int, now: datetime, getter: Callable[[str], dict] = _get_json) -> list[MolecularAtlasSource]:
    params = urlencode({"query": query, "start": 0, "size": limit,
                        "sortfield": "publicationDate", "order": "descending"})
    payload = getter(f"https://www.omicsdi.org/ws/dataset/search?{params}")
    records = []
    for item in payload.get("datasets", []):
        accession = str(item.get("id") or item.get("accession") or "").strip()
        title = str(item.get("title") or item.get("name") or "").strip()
        if not accession or not title:
            continue
        records.append(MolecularAtlasSource(
            source_id=_source_id("omicsdi", accession), source_name="OmicsDI",
            source_kind=AtlasSourceKind.PUBLIC_OMICS_DATASET, record_id=accession,
            dataset_accession=accession, title=title,
            source_url=f"https://www.omicsdi.org/dataset/{accession}",
            publication_date=str(item.get("publicationDate") or "") or None,
            layers=infer_layers(f"{title} {item.get('description', '')}"), search_query=query,
            discovered_at=now, review_status=AtlasReviewStatus.TRIAGE_REQUIRED,
            provenance_note="Discovered from OmicsDI metadata; files, sample annotations, and study design have not been reviewed.",
            data_use_note="Registry metadata only. Access, consent, controlled-access, and reuse conditions must be verified before analysis.",
        ))
    return records


def infer_layers(text: str) -> list[AtlasLayer]:
    lower = text.casefold()
    rules = {
        AtlasLayer.CELL_SOURCE: ("cell source", "donor", "stromal cell", "mesenchymal"),
        AtlasLayer.MANUFACTURING_PROCESS: ("manufactur", "culture", "bioreactor", "isolation", "purification"),
        AtlasLayer.SURFACE_CHEMISTRY: ("surface", "glyco", "membrane", "tetraspanin", "integrin"),
        AtlasLayer.RNA_CARGO: ("rna", "mirna", "transcript"),
        AtlasLayer.PROTEIN_CARGO: ("protein", "proteom", "cytokine"),
        AtlasLayer.LIPID_AND_METABOLITE_CARGO: ("lipid", "metabol"),
        AtlasLayer.SOLUBLE_SECRETOME: ("secretome", "soluble", "conditioned medium"),
        AtlasLayer.FUNCTIONAL_POTENCY: ("potency", "functional", "bioassay"),
    }
    return [layer for layer, terms in rules.items() if any(term in lower for term in terms)]


def _plain_text(value: str, *, limit: int = 4000) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return value[:limit]


def retrieve_source_material(source: MolecularAtlasSource, *, text_getter=_get_text,
                             json_getter=_get_json) -> tuple[AtlasAccessLevel, str, str]:
    """Retrieve a bounded, public source excerpt without downloading raw omics files."""
    if source.source_kind is AtlasSourceKind.PAPER:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{urlencode({'query': f'EXT_ID:{source.record_id}', 'format': 'json', 'pageSize': 1})}"
        payload = json_getter(url)
        results = payload.get("resultList", {}).get("result", [])
        if not results:
            return AtlasAccessLevel.METADATA_ONLY, "Europe PMC record metadata", source.title
        item = results[0]
        abstract = str(item.get("abstractText") or "").strip()
        if abstract:
            return AtlasAccessLevel.ABSTRACT, "Europe PMC abstract", _plain_text(abstract)
        return AtlasAccessLevel.METADATA_ONLY, "Europe PMC record metadata", _plain_text(
            " ".join(str(item.get(key) or "") for key in ("title", "journalTitle", "authorString"))
        )
    if source.source_kind is AtlasSourceKind.PUBLIC_OMICS_DATASET:
        payload = json_getter(f"https://www.omicsdi.org/ws/dataset/{source.record_id}")
        excerpt = _plain_text(" ".join(str(payload.get(key) or "") for key in (
            "title", "name", "description", "sampleDescription", "dataProtocol", "publicationDate"
        )))
        return AtlasAccessLevel.DATASET_DESCRIPTION, "OmicsDI dataset metadata", excerpt or source.title
    raise ValueError("contributed datasets require a separate governed intake pipeline")


def _build_review_package(source: MolecularAtlasSource, *, access_level: AtlasAccessLevel,
                          locator: str, excerpt: str, now: datetime) -> AtlasReviewPackage:
    layers = list(dict.fromkeys([*source.layers, *infer_layers(f"{source.title} {excerpt}")]))
    ready = bool(layers and excerpt.strip())
    limitations = [
        "Automated screening has not established study quality, reproducibility, or relevance to SGL-001 materials.",
        "Reported associations must not be treated as causal mechanisms or product specifications.",
    ]
    if access_level is AtlasAccessLevel.METADATA_ONLY:
        limitations.append("Only metadata was available; claims cannot be verified from the full report.")
    if source.source_kind is AtlasSourceKind.PUBLIC_OMICS_DATASET:
        limitations.append("Dataset files were not downloaded or analyzed; access, consent, and reuse terms remain to be reviewed.")
    return AtlasReviewPackage(
        package_id=f"atlas-review-{source.source_id.removeprefix('atlas-source-')}",
        source_id=source.source_id,
        relevance_summary=(
            "Potentially relevant to " + ", ".join(layer.value.replace("_", " ") for layer in layers)
            + "; requires human scientific review before use as SGL-001 evidence."
            if layers else "No configured Molecular Atlas layer was identified during bounded screening."
        ),
        access_level=access_level, source_locator=locator,
        source_excerpt=excerpt or source.title, extracted_layers=layers,
        limitations=limitations, ready_for_human_review=ready, processed_at=now,
    )


def run_processing(root: Path, *, max_records: int = 2, now: datetime | None = None,
                   retriever=retrieve_source_material) -> MolecularAtlasWorkspace:
    """Advance a small deterministic queue; never promote evidence automatically."""
    timestamp = now or datetime.now(timezone.utc)
    path = root / "state" / "molecular-atlas.json"
    workspace = MolecularAtlasWorkspace.model_validate_json(path.read_text(encoding="utf-8"))
    selected = [item for item in workspace.sources if item.review_status is AtlasReviewStatus.TRIAGE_REQUIRED][:max_records]
    run_id = new_run_id()
    store = RunStore(root / "atlas-runs", run_id)
    store.write_json("00-run-input.json", {"run_id": run_id, "source_ids": [item.source_id for item in selected], "max_records": max_records})
    errors: list[str] = []
    replacements: dict[str, MolecularAtlasSource] = {}
    for index, source in enumerate(selected, start=1):
        try:
            access, locator, excerpt = retriever(source)
            package = _build_review_package(source, access_level=access, locator=locator, excerpt=excerpt, now=timestamp)
            status = AtlasReviewStatus.ELIGIBLE_FOR_REVIEW if package.ready_for_human_review else AtlasReviewStatus.REJECTED
            replacements[source.source_id] = source.model_copy(update={
                "layers": package.extracted_layers or source.layers,
                "review_package": package, "review_status": status,
            })
            store.write_json(f"{index:02d}-review-package.json", package)
        except Exception as exc:
            errors.append(f"{source.source_id}: {type(exc).__name__}")
            store.write_json(f"{index:02d}-processing-error.json", {
                "source_id": source.source_id, "error_type": type(exc).__name__,
            })
    sources = [replacements.get(item.source_id, item) for item in workspace.sources]
    updated = workspace.model_copy(update={
        "sources": sources, "last_processing_at": timestamp,
        "processing_errors": errors, "updated_at": timestamp,
    })
    publish_json(path, updated)
    store.write_json("99-run-complete.json", {
        "run_id": run_id, "selected": len(selected), "processed": len(replacements),
        "errors": errors, "completed_at": timestamp,
    })
    return updated


def approve_source(root: Path, source_id: str, *, reviewer: str,
                   now: datetime | None = None) -> Evidence:
    """Human-gated promotion of one processed candidate into canonical evidence."""
    if not reviewer.strip():
        raise ValueError("reviewer identity is required")
    timestamp = now or datetime.now(timezone.utc)
    atlas_path = root / "state" / "molecular-atlas.json"
    state_path = root / "state" / "signal-state.json"
    workspace = MolecularAtlasWorkspace.model_validate_json(atlas_path.read_text(encoding="utf-8"))
    source = next((item for item in workspace.sources if item.source_id == source_id), None)
    if source is None:
        raise ValueError("unknown Molecular Atlas source")
    if source.review_status is not AtlasReviewStatus.ELIGIBLE_FOR_REVIEW or not source.review_package:
        raise ValueError("source is not eligible for human approval")
    package = source.review_package
    evidence = Evidence(
        evidence_id=f"ev-atlas-{source.source_id.removeprefix('atlas-source-')}",
        kind=(EvidenceKind.PUBLICATION if source.source_kind is AtlasSourceKind.PAPER else EvidenceKind.DATASET),
        title=source.title, source_uri=source.source_url,
        source_identifier=source.dataset_accession or source.record_id,
        locator=package.source_locator, excerpt=package.source_excerpt,
        retrieved_at=package.processed_at,
        content_sha256=hashlib.sha256(package.source_excerpt.encode()).hexdigest(),
        metadata={
            "atlas_source_id": source.source_id, "access_level": package.access_level.value,
            "layers": [item.value for item in package.extracted_layers],
            "human_reviewed_by": reviewer, "human_reviewed_at": timestamp.isoformat(),
            "limitations": package.limitations,
        },
    )
    scientific = SignalState.model_validate_json(state_path.read_text(encoding="utf-8"))
    by_id = {item.evidence_id: item for item in scientific.evidence}
    by_id[evidence.evidence_id] = evidence
    publish_json(state_path, scientific.model_copy(update={"evidence": list(by_id.values())}))
    reviewed = source.model_copy(update={
        "review_status": AtlasReviewStatus.REVIEWED,
        "approved_by": reviewer, "approved_at": timestamp,
    })
    publish_json(atlas_path, workspace.model_copy(update={
        "sources": [reviewed if item.source_id == source_id else item for item in workspace.sources],
        "updated_at": timestamp,
    }))
    return evidence


def run_discovery(root: Path, *, limit_per_query: int = 5, now: datetime | None = None,
                  paper_discoverer=discover_europe_pmc, omics_discoverer=discover_omicsdi) -> MolecularAtlasWorkspace:
    timestamp = now or datetime.now(timezone.utc)
    path = root / "state" / "molecular-atlas.json"
    workspace = (MolecularAtlasWorkspace.model_validate_json(path.read_text())
                 if path.exists() else initial_molecular_atlas(now=timestamp))
    discovered: list[MolecularAtlasSource] = []
    errors: list[str] = []
    for query in workspace.search_queries:
        for source_name, discoverer in (("Europe PMC", paper_discoverer), ("OmicsDI", omics_discoverer)):
            try:
                discovered.extend(discoverer(query, limit=limit_per_query, now=timestamp))
            except Exception as exc:  # keep prior state when a registry is unavailable
                errors.append(
                    f"{source_name} discovery failed for one configured query: {type(exc).__name__}"
                )
    existing = {item.source_id: item for item in workspace.sources}
    for item in discovered:
        existing.setdefault(item.source_id, item)
    sources = sorted(existing.values(), key=lambda item: item.discovered_at, reverse=True)
    coverage = []
    for item in workspace.coverage:
        candidates = sum(item.layer in source.layers for source in sources)
        reviewed = sum(item.layer in source.layers and source.review_status is AtlasReviewStatus.REVIEWED for source in sources)
        coverage.append(item.model_copy(update={"candidate_source_count": candidates, "reviewed_source_count": reviewed}))
    updated = workspace.model_copy(update={"sources": sources, "coverage": coverage,
                                            "last_discovery_at": timestamp, "updated_at": timestamp,
                                            "discovery_errors": errors})
    publish_json(path, updated)
    return updated


def export_molecular_atlas(workspace: MolecularAtlasWorkspace) -> PublicMolecularAtlas:
    counts = {status.value: sum(item.review_status is status for item in workspace.sources) for status in AtlasReviewStatus}
    counts["papers"] = sum(item.source_kind is AtlasSourceKind.PAPER for item in workspace.sources)
    counts["public_omics_datasets"] = sum(item.source_kind is AtlasSourceKind.PUBLIC_OMICS_DATASET for item in workspace.sources)
    return PublicMolecularAtlas(
        title="SGL-001 Molecular Atlas",
        subtitle="Connecting cell source and manufacturing to surface chemistry, cargo, secretome composition, and functional potency.",
        disclaimer="Discovered records are candidates for human review, not validated SGL-001 evidence, product specifications, clinical findings, or automatic model-training data.",
        layers=workspace.coverage,
        current_questions=[
            "Which surface and cargo attributes are reproducible across lots?",
            "Which process variables explain composition changes?",
            "Which composition patterns predict a relevant potency response?",
            "What measurements distinguish vesicular from soluble secretome activity?",
        ], discovery_counts=counts,
        source_status=("All configured sources responded." if not workspace.discovery_errors
                       else "One or more sources were unavailable; prior records were preserved."),
        processing_status=(
            "Candidate processing is current."
            if not workspace.processing_errors
            else "One or more candidates could not be processed; they remain queued for a later run."
        ),
        recent_discoveries=[PublicAtlasDiscovery(
            source_id=item.source_id, source_name=item.source_name,
            source_kind=item.source_kind, record_id=item.record_id, title=item.title,
            source_url=item.source_url, publication_date=item.publication_date,
            dataset_accession=item.dataset_accession, layers=item.layers,
            review_status=item.review_status,
            relevance_summary=(item.review_package.relevance_summary if item.review_package else None),
            access_level=(item.review_package.access_level if item.review_package else None),
            processed_at=(item.review_package.processed_at if item.review_package else None),
        ) for item in workspace.sources[:12]],
        contribution_headline="Contribute to the Signal Molecular Atlas",
        contribution_description="Share well-annotated EV and secretome datasets to help evaluate reproducible product signatures and generate testable hypotheses.",
        contribution_fields=[
            AtlasContributionField(field_id="dataset-type", label="Dataset and assay type", required=True, help_text="For example RNA-seq, proteomics, lipidomics, surface profiling, or potency."),
            AtlasContributionField(field_id="sample-provenance", label="Sample provenance", required=True, help_text="Species, tissue or cell source, donor context, and cohort structure."),
            AtlasContributionField(field_id="process-metadata", label="Process metadata", required=True, help_text="Culture, conditioning, harvest, isolation, storage, lot, and batch information."),
            AtlasContributionField(field_id="methods-controls", label="Methods and controls", required=True, help_text="Protocols, platform, replicates, controls, normalization, and QC."),
            AtlasContributionField(field_id="access-rights", label="Consent, access, and reuse rights", required=True, help_text="Data-use limitations, participant consent, license, and desired attribution."),
            AtlasContributionField(field_id="record-location", label="Repository accession or dataset description", required=True, help_text="Register metadata first; do not upload files or participant data here."),
        ],
        contribution_steps=["Register dataset metadata", "Scientific and governance review", "Document rights and permitted uses", "Controlled data transfer", "QC and harmonization", "Human-reviewed analysis and publication"],
        accepted_data_types=["Small-RNA and transcriptomics", "Proteomics and surface proteomics", "Lipidomics, metabolomics, and glycomics", "Soluble-factor panels", "Particle identity, purity, and morphology", "Manufacturing and lot metadata", "Functional and potency assays"],
        prohibited_submission="Do not submit patient identifiers, protected health information, credentials, confidential files, or human-level omics through the public website.",
        cta_primary="Register a dataset", cta_secondary="Discuss a collaboration",
        last_discovery_at=workspace.last_discovery_at,
        last_processing_at=workspace.last_processing_at,
    )
