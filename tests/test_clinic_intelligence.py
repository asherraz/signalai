import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from signalai.clinic_intelligence import ClinicIngestor, DeterministicClinicExtractionClient, assess_clinic_fit, clinic_id_for, normalize_url
from signalai.clinic_intelligence_export import export_clinic_intelligence
from signalai.schemas.clinic_intelligence import (
    ClinicExtraction, ClinicIntelligenceDataset, ClinicOutreachCandidate,
    ClinicProfile, ClinicTherapy, SourceField,
)


NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)
HOME = "https://example-clinic.test/"
ABOUT = "https://example-clinic.test/about"
SERVICES = "https://example-clinic.test/treatments"
PAGES = {
    HOME: '<html><body><h1>Example Clinic</h1><a href="/treatments">Treatments</a><a href="/about">About</a><a href="/contact">Contact</a><script>private token</script></body></html>',
    SERVICES: '<html><body><p>We offer exosome therapy and intranasal delivery for cognitive wellness.</p><p>Autologous stem cell therapy and IV care.</p></body></html>',
    ABOUT: '<html><body><p>Our research team studies regenerative medicine.</p></body></html>',
    "https://example-clinic.test/contact": '<html><body><p>Contact our clinic.</p></body></html>',
}


def _field(field, value, source_url, excerpt):
    return SourceField(field=field, value=value, source_url=source_url, source_excerpt=excerpt, confidence="high")


def _extraction():
    return ClinicExtraction(fields=[
        _field("name", "Example Clinic", HOME, "Example Clinic"),
        _field("therapies_offered", "exosomes_evs", SERVICES, "exosome therapy"),
        _field("therapies_offered", "autologous_stem_cells", SERVICES, "Autologous stem cell therapy"),
        _field("routes_of_administration", "intranasal", SERVICES, "intranasal delivery"),
        _field("routes_of_administration", "iv", SERVICES, "IV care"),
        _field("indications", "cognitive wellness", SERVICES, "cognitive wellness"),
        _field("exosome_or_ev_offering", True, SERVICES, "exosome therapy"),
    ])


class FakeClient:
    def __init__(self, extraction=None):
        self.extraction = extraction or _extraction()
        self.calls = []
        self.usage_records = []

    def generate(self, *, instructions, input_text, output_type):
        self.calls.append(json.loads(input_text))
        assert output_type is ClinicExtraction
        assert "<html" not in input_text
        assert "private token" not in input_text
        self.usage_records.append({"model": "test-small", "input_tokens": 500, "output_tokens": 80, "estimated_api_cost_usd": 0.0003})
        return self.extraction


def _ingestor(tmp_path, client=None, max_pages=3, fetcher=None):
    calls = []
    def fetch(url):
        calls.append(url)
        return PAGES[url]
    return ClinicIngestor(root=tmp_path, client=client or FakeClient(), fetcher=fetcher or fetch,
                          max_pages=max_pages, now_factory=lambda: NOW), calls


def test_clinic_url_ingestion_is_bounded_and_provenance_checked(tmp_path):
    client = FakeClient()
    ingestor, fetched = _ingestor(tmp_path, client)
    profile, fit, changed = ingestor.ingest(HOME)
    assert changed and len(fetched) == 3
    assert len(client.calls) == 1
    assert profile.clinic_id == clinic_id_for(HOME)
    assert profile.exosome_or_ev_offering is True
    assert ClinicTherapy.EXOSOMES_EVS in profile.therapies_offered
    assert profile.routes_of_administration == ["intranasal", "iv"]
    assert profile.indications == ["cognitive wellness"]
    assert profile.country is None and profile.city is None
    assert all(item.source_excerpt for item in profile.provenance)
    assert fit.sgl001_relevance == "high"
    assert fit.jurisdiction_fit == "not_assessed"
    private = next((tmp_path / "data/clinics/private-runs").iterdir())
    assert json.loads(private.read_text())["pages_fetched"] == 3
    assert json.loads(private.read_text())["usage"][0]["estimated_api_cost_usd"] == 0.0003
    assert len(list((tmp_path / "data/clinics/history" / profile.clinic_id).iterdir())) == 1


def test_unknown_is_not_inferred_and_unsourced_claim_is_rejected(tmp_path):
    invalid = ClinicExtraction(fields=[_field("country", "United States", HOME, "not on page")])
    ingestor, _ = _ingestor(tmp_path, FakeClient(invalid))
    with pytest.raises(ValueError, match="unverified source excerpt"):
        ingestor.ingest(HOME)
    assert not (tmp_path / "data/clinics/clinics.json").exists()
    unsupported = ClinicExtraction(fields=[_field("country", "United States", HOME, "Example Clinic")])
    ingestor, _ = _ingestor(tmp_path, FakeClient(unsupported))
    with pytest.raises(ValueError, match="does not contain country value"):
        ingestor.ingest(HOME)


def test_duplicate_ingest_is_cached_and_changed_page_refresh_preserves_history(tmp_path):
    client = FakeClient()
    pages = dict(PAGES)
    fetched = []
    def fetch(url):
        fetched.append(url)
        return pages[url]
    ingestor, _ = _ingestor(tmp_path, client, fetcher=fetch)
    first, _, _ = ingestor.ingest(HOME)
    count = len(fetched)
    same, _, changed = ingestor.ingest(HOME)
    assert not changed and same == first and len(fetched) == count
    _, _, changed = ingestor.ingest(HOME, refresh=True)
    assert not changed and len(client.calls) == 1
    pages[ABOUT] += '<p>New public information.</p>'
    _, _, changed = ingestor.ingest(HOME, refresh=True)
    assert changed and len(client.calls) == 2
    dataset = ClinicIntelligenceDataset.model_validate_json((tmp_path / "data/clinics/clinics.json").read_text())
    assert len(dataset.profiles) == 1 and len(dataset.fits) == 1
    assert len(list((tmp_path / "data/clinics/history" / first.clinic_id).iterdir())) == 2


def test_public_projection_excludes_private_outreach_and_usage(tmp_path):
    ingestor, _ = _ingestor(tmp_path)
    profile, fit, _ = ingestor.ingest(HOME)
    outreach = ClinicOutreachCandidate(
        clinic_id=profile.clinic_id, why_relevant="Internal diligence", sgl001_fit="high",
        recommended_ask="Private ask", recommended_relationship_level="intelligence_prospect",
        priority="high",
    )
    dataset = ClinicIntelligenceDataset(profiles=[profile], fits=[fit], outreach_queue=[outreach])
    payload = export_clinic_intelligence(dataset).model_dump(mode="json", by_alias=True)
    assert payload["summary"]["clinicsIndexed"] == 1
    assert payload["summary"]["exosomeClinics"] == 1
    assert payload["topMatches"][0]["clinicId"] == profile.clinic_id
    serialized = json.dumps(payload)
    for forbidden in ("Private ask", "Internal diligence", "estimated_api_cost", "sourceExcerpt", "contact_email"):
        assert forbidden not in serialized


def test_batch_bounds_and_no_automatic_outreach(tmp_path):
    ingestor, _ = _ingestor(tmp_path)
    with pytest.raises(ValueError, match="batch exceeds"):
        ingestor.batch([f"https://clinic-{i}.test/" for i in range(6)])
    profile, _, _ = ingestor.ingest(HOME)
    dataset = ClinicIntelligenceDataset.model_validate_json((tmp_path / "data/clinics/clinics.json").read_text())
    assert profile.clinic_id == dataset.profiles[0].clinic_id
    assert dataset.outreach_queue == []
    with pytest.raises(ValueError, match="human approver"):
        ClinicOutreachCandidate(clinic_id=profile.clinic_id, why_relevant="Relevant",
            sgl001_fit="high", recommended_ask="Contact", recommended_relationship_level="advisory_partner",
            priority="high", status="approved")


def test_nonpublic_urls_rejected():
    for url in ("file:///etc/passwd", "http://localhost/", "http://127.0.0.1/", "http://10.0.0.2/"):
        with pytest.raises(ValueError):
            normalize_url(url)


def test_deterministic_fallback_emits_only_literal_page_claims(tmp_path):
    ingestor, _ = _ingestor(tmp_path, client=DeterministicClinicExtractionClient())
    profile, fit, changed = ingestor.ingest(HOME)
    assert changed
    assert profile.name == "Example Clinic"
    assert profile.exosome_or_ev_offering is True
    assert profile.country is None
    assert all(item.source_excerpt for item in profile.provenance)
    assert fit.jurisdiction_fit == "not_assessed"
    private = next((tmp_path / "data/clinics/private-runs").iterdir())
    assert json.loads(private.read_text())["usage"][0]["estimated_api_cost_usd"] == 0.0


def test_first_validation_seeds_and_canonical_urls_are_exact():
    root = Path(__file__).resolve().parents[1]
    seeds = json.loads((root / "data/clinic-seeds.json").read_text())
    assert seeds == [
        "https://floridaregenerative.com/",
        "https://www.revivflorida.com/",
        "https://stemcellxo.com/",
        "https://www.orlandostemcellcenter.com/",
        "https://exos.miami/",
        "https://www.thehundred.jp/en/clinic/",
    ]
    dataset = ClinicIntelligenceDataset.model_validate_json((root / "data/clinics/clinics.json").read_text())
    assert {str(item.website) for item in dataset.profiles} == set(seeds)
    assert dataset.outreach_queue == []
