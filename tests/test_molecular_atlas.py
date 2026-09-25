from datetime import datetime, timezone
from pathlib import Path

from signalai.molecular_atlas import (
    discover_europe_pmc, discover_omicsdi, export_molecular_atlas,
    initial_molecular_atlas, run_discovery,
)
from signalai.schemas.molecular_atlas import AtlasReviewStatus, AtlasSourceKind


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
