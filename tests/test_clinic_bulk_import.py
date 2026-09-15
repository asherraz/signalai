import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import RootModel

from signalai.clinic_index import import_clinic_profiles, load_seeds, validate_seed_geography, enrich_selected
from signalai.clinic_intelligence import ClinicIngestor, DeterministicClinicExtractionClient
from signalai.clinic_intelligence_export import export_clinic_intelligence
from signalai.schemas.clinic_intelligence import ClinicSeed, ClinicIntelligenceDataset, ClinicProfile, SourceField
from signalai.storage import publish_json

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def test_supplied_100_import_is_discovery_only_and_idempotent(tmp_path):
    source = ROOT / "data/clinic-seeds.json"
    seeds = load_seeds(source)
    validate_seed_geography(seeds, ROOT / "data/signal_clinic_seeds_100_summary.json")
    assert Counter(seed.region for seed in seeds) == {"Asia": 50, "United States": 25, "Rest of World": 25}
    report = import_clinic_profiles(tmp_path, source, now_factory=lambda: NOW)
    assert report == {"imported": 100, "merged": 0, "duplicates": 0, "invalid": 0, "skipped": 0, "total_indexed": 100}
    dataset = ClinicIntelligenceDataset.model_validate_json((tmp_path / "data/clinics/clinics.json").read_text())
    assert all(profile.profile_state == "indexed" and profile.review_status == "unreviewed" for profile in dataset.profiles)
    assert all(not profile.therapies_offered and not profile.regulatory_or_licensing_claims for profile in dataset.profiles)
    assert all(profile.discovery_records for profile in dataset.profiles)
    assert not dataset.outreach_queue
    assert not (tmp_path / "state/clinical-network.json").exists()
    public = export_clinic_intelligence(dataset).model_dump(mode="json", by_alias=True)
    assert public["summary"]["clinicsByRegion"] == {"Asia": 50, "United States": 25, "Rest of World": 25}
    assert public["summary"]["countries"] == 20
    assert public["summary"]["clinicsEnriched"] == 0
    allowed = {"clinicId", "name", "website", "city", "country", "region", "profileState"}
    assert all(set(profile) == allowed for profile in public["clinics"])
    assert import_clinic_profiles(tmp_path, source, now_factory=lambda: NOW)["skipped"] == 100


def test_geography_error_aborts_before_state_writes(tmp_path):
    seeds = load_seeds(ROOT / "data/clinic-seeds.json")
    with pytest.raises(ValueError, match="geography invalid"):
        validate_seed_geography(seeds[:-1], ROOT / "data/signal_clinic_seeds_100_summary.json")
    changed = [*seeds]
    changed[0] = changed[0].model_copy(update={"region": "Rest of World"})
    with pytest.raises(ValueError, match="geography invalid"):
        validate_seed_geography(changed, ROOT / "data/signal_clinic_seeds_100_summary.json")
    source = tmp_path / "data/clinic-seeds.json"
    publish_json(source, RootModel[list[ClinicSeed]](seeds[:-1]))
    publish_json(tmp_path / "data/signal_clinic_seeds_100_summary.json", RootModel[dict](json.loads((ROOT / "data/signal_clinic_seeds_100_summary.json").read_text())))
    with pytest.raises(ValueError, match="geography invalid"):
        import_clinic_profiles(tmp_path, source)
    assert not (tmp_path / "data/clinics/clinics.json").exists()


def test_domain_duplicate_sources_merge_and_keep_rich_profile(tmp_path):
    url = "https://example-clinic.test/"
    profile = ClinicProfile(clinic_id="clinic-original", name="Verified Clinic", website=url,
        therapies_offered=["msc"], source_urls=[url], last_checked_at=NOW,
        provenance=[SourceField(field="name", value="Verified Clinic", source_url=url, source_excerpt="Verified Clinic"),
                    SourceField(field="therapies_offered", value="msc", source_url=url, source_excerpt="We offer MSC therapy")])
    publish_json(tmp_path / "data/clinics/clinics.json", ClinicIntelligenceDataset(profiles=[profile]))
    seeds = [ClinicSeed(name_hint="Weaker Directory Name", url=url, country_hint="Japan", city_hint="Tokyo", region="Asia", discovery_source="directory-one"),
             ClinicSeed(name_hint="Weaker Directory Name", url="http://www.example-clinic.test/", country_hint="Japan", city_hint="Tokyo", region="Asia", discovery_source="directory-two")]
    source = tmp_path / "seeds.json"
    publish_json(source, RootModel[list[ClinicSeed]](seeds))
    report = import_clinic_profiles(tmp_path, source, now_factory=lambda: NOW)
    assert report["imported"] == 0
    assert report["duplicates"] == 1
    dataset = ClinicIntelligenceDataset.model_validate_json((tmp_path / "data/clinics/clinics.json").read_text())
    actual = dataset.profiles[0]
    assert actual.name == "Verified Clinic"
    assert actual.clinic_id == "clinic-original"
    assert actual.therapies_offered == profile.therapies_offered
    assert actual.provenance == profile.provenance
    assert actual.profile_state == "enriched"
    assert actual.discovery_sources == ["directory-one", "directory-two"]
    assert len(actual.discovery_records) == 2


def test_ten_enrichment_bound_filters_and_cached_content(tmp_path):
    seeds = [ClinicSeed(name_hint=f"Example Clinic {index}", url=f"https://clinic-{index}.test/", city_hint="Tokyo", country_hint="Japan", region="Asia", discovery_source="manual", priority=1) for index in range(12)]
    source = tmp_path / "seeds.json"
    publish_json(source, RootModel[list[ClinicSeed]](seeds))
    import_clinic_profiles(tmp_path, source, now_factory=lambda: NOW)
    client = DeterministicClinicExtractionClient()
    fetched = []
    def fetch(url):
        fetched.append(url)
        return "<h1>Example Clinic</h1><p>We offer stem cell therapy.</p>"
    ingestor = ClinicIngestor(root=tmp_path, client=client, fetcher=fetch, max_clinics=10, now_factory=lambda: NOW)
    assert enrich_selected(ingestor, seeds, region="Rest of World", country="Japan") == []
    assert enrich_selected(ingestor, seeds, country="United States") == []
    result = enrich_selected(ingestor, seeds, limit=10, region="Asia", country="Japan", priority=1, only_new=True)
    assert len(result) == 10
    assert len(fetched) == 10
    assert len(client.usage_records) == 10
    assert sum(profile.profile_state == "enriched" for profile in ingestor._dataset().profiles) == 10
    assert all(profile.region == "Asia" for profile in ingestor._dataset().profiles)
    enrich_selected(ingestor, seeds, limit=10)
    assert len(client.usage_records) == 10  # Same cleaned content: no repeated extraction.
