from datetime import datetime, timezone
from pathlib import Path

from signalai.molecular_atlas import (
    approve_source, discover_europe_pmc, discover_omicsdi, export_molecular_atlas,
    initial_molecular_atlas, run_discovery, run_processing,
)
from signalai.schemas.molecular_atlas import AtlasAccessLevel, AtlasReviewStatus, AtlasSourceKind
from signalai.storage import publish_json
from signalai.schemas.models import SignalState


NOW = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)


def test_discovery_adapters_create_provenance_linked_candidates():
    papers = discover_europe_pmc("EV surface", limit=2, now=NOW, getter=lambda _: {
        "resultList": {"result": [{"pmid": "123", "title": "MSC EV surface proteomics", "pubYear": "2026"}]}
    })
    datasets = discover_omicsdi("EV cargo", limit=2, now=NOW, getter=lambda _: {
        "datasets": [{"id": "PXD000001", "title": "Extracellular vesicle proteomics"}]
    })
    assert papers[0].source_kind is AtlasSourceKind.PAPER
    assert datasets[0].source_kind is AtlasSourceKind.PUBLIC_OMICS_DATASET
    assert papers[0].review_status is AtlasReviewStatus.TRIAGE_REQUIRED
    assert papers[0].layers


def test_discovery_is_append_only_and_deduplicated(tmp_path: Path):
    (tmp_path / "state").mkdir()
    paper = lambda query, limit, now: discover_europe_pmc(query, limit=limit, now=now, getter=lambda _: {
        "resultList": {"result": [{"pmid": "123", "title": "MSC EV surface proteomics"}]}
    })
    empty = lambda query, limit, now: []
    first = run_discovery(tmp_path, now=NOW, paper_discoverer=paper, omics_discoverer=empty)
    second = run_discovery(tmp_path, now=NOW, paper_discoverer=paper, omics_discoverer=empty)
    assert len(first.sources) == 1
    assert len(second.sources) == len(first.sources)


def test_public_projection_never_claims_discoveries_are_evidence():
    public = export_molecular_atlas(initial_molecular_atlas(now=NOW))
    assert "not validated SGL-001 evidence" in public.disclaimer
    assert "Do not submit patient identifiers" in public.prohibited_submission
    assert public.cta_primary == "Register a dataset"


def test_processing_advances_only_a_bounded_queue(tmp_path: Path):
    (tmp_path / "state").mkdir()
    paper = lambda query, limit, now: discover_europe_pmc(query, limit=limit, now=now, getter=lambda _: {
        "resultList": {"result": [
            {"pmid": "123", "title": "MSC EV surface proteomics"},
            {"pmid": "124", "title": "MSC EV miRNA cargo"},
            {"pmid": "125", "title": "MSC secretome potency assay"},
        ]}
    })
    workspace = run_discovery(tmp_path, now=NOW, paper_discoverer=paper, omics_discoverer=lambda **_: [])
    assert len(workspace.sources) == 3
    processed = run_processing(
        tmp_path, max_records=2, now=NOW,
        retriever=lambda source: (AtlasAccessLevel.ABSTRACT, "Abstract", f"{source.title} reports surface protein and RNA measurements."),
    )
    assert sum(item.review_status is AtlasReviewStatus.ELIGIBLE_FOR_REVIEW for item in processed.sources) == 2
    assert sum(item.review_status is AtlasReviewStatus.TRIAGE_REQUIRED for item in processed.sources) == 1
    assert len(list((tmp_path / "atlas-runs").iterdir())) == 1


def test_only_human_approval_promotes_canonical_evidence(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "state").mkdir()
    scientific = SignalState.model_validate_json((root / "state/signal-state.json").read_text())
    publish_json(tmp_path / "state/signal-state.json", scientific)
    paper = lambda query, limit, now: discover_europe_pmc(query, limit=limit, now=now, getter=lambda _: {
        "resultList": {"result": [{"pmid": "123", "title": "MSC EV surface proteomics"}]}
    })
    run_discovery(tmp_path, now=NOW, paper_discoverer=paper, omics_discoverer=lambda **_: [])
    processed = run_processing(
        tmp_path, max_records=1, now=NOW,
        retriever=lambda source: (AtlasAccessLevel.ABSTRACT, "Abstract", "MSC extracellular vesicle surface proteomics report."),
    )
    source = processed.sources[0]
    assert len(SignalState.model_validate_json((tmp_path / "state/signal-state.json").read_text()).evidence) == len(scientific.evidence)
    evidence = approve_source(tmp_path, source.source_id, reviewer="reviewer-1", now=NOW)
    updated = SignalState.model_validate_json((tmp_path / "state/signal-state.json").read_text())
    assert evidence.evidence_id in {item.evidence_id for item in updated.evidence}
    assert len(updated.evidence) == len(scientific.evidence) + 1
