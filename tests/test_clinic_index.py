import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from signalai.clinic_index import ClinicIndexer, enrich_selected, import_seeds, load_seeds, select_seeds
from signalai.clinic_intelligence import ClinicIngestor, DeterministicClinicExtractionClient
from signalai.clinic_intelligence_export import export_clinic_intelligence
from signalai.schemas.clinic_intelligence import ClinicProfile, ClinicSeed


NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)
URL = "https://example-clinic.test/"
HTML = "<h1>Example Clinic</h1><p>We offer stem cell therapy and exosome therapy.</p><p>Located in Test City, Test Country.</p>"


def seed(url=URL, **kwargs):
    return ClinicSeed(url=url, name_hint="Example Clinic", city_hint="Test City", country_hint="Test Country", discovery_source="https://public-directory.test/clinics", **kwargs)


def indexer(tmp_path, html=HTML):
    return ClinicIndexer(root=tmp_path, fetcher=lambda url: html, now_factory=lambda: NOW)


def test_basic_index_is_sourced_unreviewed_and_not_a_partner(tmp_path):
    engine = indexer(tmp_path)
    assert engine.index([seed()])[0]["status"] == "indexed"
    profile = engine.dataset().profiles[0]
    assert profile.profile_state == "indexed"
    assert profile.review_status == "unreviewed"
    assert profile.confidence == "low"
    assert profile.name == "Example Clinic"
    assert profile.country == "Test Country"
    assert profile.physicians == []
    assert profile.discovery_sources == [seed().discovery_source]
    assert all(item.source_url == profile.website for item in profile.provenance)
    payload = export_clinic_intelligence(engine.dataset()).model_dump(mode="json", by_alias=True)
    assert payload["summary"]["clinicsIndexed"] == 1
    assert payload["summary"]["clinicsEnriched"] == 0
    assert payload["summary"]["stemCellClinics"] == 0
    assert payload["summary"]["exosomeClinics"] == 0
    assert payload["summary"]["clinicsByCountry"] == {"Test Country": 1}
    assert payload["summary"]["clinicsByTherapy"] == {}
    assert payload["clinics"][0]["profileState"] == "indexed"
    assert not engine.dataset().outreach_queue
    assert not (tmp_path / "state/clinical-network.json").exists()
    text = json.dumps(payload)
    assert "discovery_sources" not in text
    assert "estimated_api_cost" not in text
    assert "partner_status" not in text


def test_index_requires_name_offering_and_provenance(tmp_path):
    assert indexer(tmp_path, "<h1>Example Clinic</h1><p>Stem cells are an area of research.</p>").index([seed()])[0]["status"] == "skipped"
    assert not indexer(tmp_path).dataset().profiles
    with pytest.raises(ValidationError, match="sourced canonical name"):
        ClinicProfile(clinic_id="clinic-one", website=URL, profile_state="indexed", last_checked_at=NOW)
    with pytest.raises(ValidationError, match="provenance"):
        ClinicProfile(clinic_id="clinic-one", website=URL, name="Unverified", profile_state="indexed", therapies_offered=["msc"], last_checked_at=NOW)


def test_hints_are_not_inferred_facts(tmp_path):
    engine = indexer(tmp_path, "<h1>Example Clinic</h1><p>We offer stem cell therapy.</p>")
    engine.index([seed()])
    assert engine.dataset().profiles[0].city is None
    assert engine.dataset().profiles[0].country is None


def test_domains_and_scoped_names_are_deduplicated(tmp_path):
    engine = indexer(tmp_path)
    result = engine.index([seed(), seed("http://www.example-clinic.test/treatments"), seed("https://other-site.test/")])
    assert len(result) == 2
    assert len(engine.dataset().profiles) == 1
    assert result[1]["status"] == "duplicate_name_location"
    assert engine.index([seed("https://www.example-clinic.test/")])[0]["status"] == "already_indexed"


def test_only_new_filters_before_limit_and_priority_country_filters(tmp_path):
    engine = indexer(tmp_path)
    engine.index([seed()])
    second = seed("https://second-clinic.test/", priority=1)
    report = engine.index([seed(), second], only_new=True, limit=1, priority=1, country="Test Country")
    assert report[0]["url"] == str(second.url)
    assert select_seeds([seed(enabled=False)]) == []
    assert select_seeds([seed()], country="Elsewhere") == []
    with pytest.raises(ValueError):
        select_seeds([seed()], limit=0)


def test_enrichment_upgrades_with_same_id_and_history(tmp_path):
    engine = indexer(tmp_path)
    engine.index([seed()])
    original_id = engine.dataset().profiles[0].clinic_id
    ingestor = ClinicIngestor(root=tmp_path, client=DeterministicClinicExtractionClient(), fetcher=lambda url: HTML, now_factory=lambda: NOW)
    results = enrich_selected(ingestor, [seed("https://www.example-clinic.test/")], only_new=True)
    assert results[0][2]
    profile = engine.dataset().profiles[0]
    assert profile.clinic_id == original_id
    assert profile.profile_state == "enriched"
    assert profile.review_status == "unreviewed"
    assert profile.discovery_sources == [seed().discovery_source]
    history = list((tmp_path / "data/clinics/history" / original_id).glob("*.json"))
    assert len(history) == 2
    assert {json.loads(path.read_text())["profile_state"] for path in history} == {"indexed", "enriched"}
    assert enrich_selected(ingestor, [seed()], only_new=True) == []
    with pytest.raises(ValueError):
        enrich_selected(ingestor, [seed()], limit=20)


def test_discovery_import_preserves_source_and_legacy_lists(tmp_path):
    from pydantic import RootModel
    from signalai.storage import publish_json

    source = tmp_path / "directory.json"
    publish_json(source, RootModel[list[ClinicSeed]]([seed(), seed("https://www.example-clinic.test/")]))
    assert import_seeds(tmp_path, source) == 1
    assert import_seeds(tmp_path, source) == 0
    assert load_seeds(tmp_path / "data/clinic-seeds.json")[0].discovery_source == seed().discovery_source
    legacy = tmp_path / "urls.json"
    publish_json(legacy, RootModel[list[str]]([URL]))
    assert str(load_seeds(legacy)[0].url) == URL


def test_large_seed_import_advances_in_bounded_batches(tmp_path):
    from pydantic import RootModel
    from signalai.storage import publish_json

    source = tmp_path / "directory.json"
    publish_json(source, RootModel[list[ClinicSeed]]([seed(f"https://clinic-{index}.test/") for index in range(7)]))
    assert [import_seeds(tmp_path, source, limit=3) for _ in range(4)] == [3, 3, 1, 0]
    assert len(load_seeds(tmp_path / "data/clinic-seeds.json")) == 7


@pytest.mark.parametrize("command", ["clinic-discover", "clinic-index", "clinic-enrich"])
def test_cli_dispatches_index_commands_and_filters(monkeypatch, command):
    import sys
    import signalai.__main__ as entry

    captured = []
    monkeypatch.setattr(entry, "clinic_index_main", lambda *args, **kwargs: captured.append((args, kwargs)))
    monkeypatch.setattr(sys, "argv", ["signalai", command, "seeds.json", "--limit", "2", "--country", "Japan", "--priority", "1", "--only-new"])
    entry.main()
    assert captured == [((command, "seeds.json"), {"limit": 2, "country": "Japan", "region": None, "priority": 1, "only_new": True})]
