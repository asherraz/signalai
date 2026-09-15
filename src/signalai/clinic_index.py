"""Seed import and one-page deterministic indexing, independent of enrichment."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from pydantic import RootModel

from signalai.clinic_intelligence import (
    ClinicIngestor, DeterministicClinicExtractionClient, _profile_from_extraction,
    assess_clinic_fit, clean_html, clinic_domain, clinic_id_for, fetch_html, normalize_url,
)
from signalai.schemas.clinic_intelligence import (
    ClinicExtraction, ClinicIntelligenceDataset, ClinicProfile, ClinicProfileState,
    ClinicSeed, SourceField,
)
from signalai.storage import new_run_id, publish_json


def load_seeds(path: Path) -> list[ClinicSeed]:
    """Legacy URL lists remain readable; directory exports use the typed seed contract."""
    if path.suffix == ".json":
        records = json.loads(path.read_text())
        if not isinstance(records, list):
            raise ValueError("clinic seeds must be a JSON array")
    else:
        records = [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    return [ClinicSeed(url=item, discovery_source=f"manual_list:{path.name}") if isinstance(item, str) else ClinicSeed.model_validate(item) for item in records]


def select_seeds(seeds, *, limit=25, country=None, region=None, priority=None):
    if not 1 <= limit <= 1000:
        raise ValueError("index/import limit must be between 1 and 1000")
    if priority is not None and not 1 <= priority <= 5:
        raise ValueError("priority must be between 1 and 5 (1 is highest)")
    chosen = sorted((seed for seed in seeds if seed.enabled
                     and (country is None or (seed.country_hint or "").casefold() == country.casefold())
                     and (region is None or (seed.region or "").casefold() == region.casefold())
                     and (priority is None or seed.priority <= priority)), key=lambda seed: (seed.priority, str(seed.url)))
    seen = set()
    result = []
    for seed in chosen:
        key = clinic_domain(str(seed.url))
        if key not in seen:
            result.append(seed)
            seen.add(key)
    return result[:limit]


def import_seeds(root: Path, source: Path, **filters) -> int:
    """Import explicitly supplied directory JSON/URL files; never crawl directories."""
    path = root / "data/clinic-seeds.json"
    existing = load_seeds(path) if path.exists() else []
    known = {clinic_domain(str(seed.url)) for seed in existing}
    # Filter existing domains before limiting, so repeated bounded imports can
    # advance through a large directory export rather than stall at its first page.
    additions = select_seeds([seed for seed in load_seeds(source) if clinic_domain(str(seed.url)) not in known], **filters)
    publish_json(path, RootModel[list[ClinicSeed]]([*existing, *additions]))
    return len(additions)


def _name_key(profile):
    # Same-name clinics in different/unknown locations are not safely equivalent.
    if not profile.country or not profile.city or not profile.name:
        return None
    return (re.sub(r"\W+", "", profile.name.casefold()), profile.city.casefold(), profile.country.casefold())


def validate_seed_geography(seeds: list[ClinicSeed], summary_path: Path) -> None:
    expected = {"Asia": 50, "United States": 25, "Rest of World": 25}
    summary = json.loads(summary_path.read_text())
    actual = dict(Counter(seed.region for seed in seeds))
    if len(seeds) != 100 or actual != expected or summary.get("total") != 100 or summary.get("region_counts") != expected:
        raise ValueError(f"canonical seed geography invalid: total={len(seeds)}, regions={actual}; expected 100 and {expected}")


def _normalized_text(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()) if value else None


def import_clinic_profiles(root: Path, source: Path, *, now_factory=lambda: datetime.now(timezone.utc)):
    """Bulk discovery records: zero fetches, no treatment facts from seed hints."""
    seeds = load_seeds(source)
    summary = root / "data/signal_clinic_seeds_100_summary.json"
    if summary.exists():
        validate_seed_geography(seeds, summary)
    dataset = ClinicIndexer(root=root).dataset()
    profiles = {item.clinic_id: item for item in dataset.profiles}
    domains = {clinic_domain(str(item.website)): item.clinic_id for item in dataset.profiles}
    names = {_name_key(item): item.clinic_id for item in dataset.profiles if _name_key(item)}
    counts = {"imported": 0, "merged": 0, "duplicates": 0, "invalid": 0, "skipped": 0}
    seen = set()
    snapshots = []
    now = now_factory()
    for original in seeds:
        if not original.enabled:
            counts["skipped"] += 1
            continue
        try:
            home = normalize_url(str(original.url))
            domain = clinic_domain(home)
            seed = original.model_copy(update={field: _normalized_text(getattr(original, field)) for field in ("name_hint", "city_hint", "country_hint", "region")})
            if not seed.name_hint:
                raise ValueError("bulk import requires name_hint")
            # Preserve the supplied retrieval path; domain keys collapse www/scheme.
            candidate = ClinicProfile(clinic_id=clinic_id_for("https://" + domain),
                name=seed.name_hint, website=home, city=seed.city_hint, country=seed.country_hint,
                region=seed.region, discovery_records=[seed], discovery_sources=[seed.discovery_source],
                last_checked_at=now, confidence="low", profile_state="indexed")
            existing_id = domains.get(domain) or names.get(_name_key(candidate))
            if domain in seen:
                counts["duplicates"] += 1
            seen.add(domain)
            if existing_id:
                existing = profiles[existing_id]
                records = list(existing.discovery_records)
                if seed not in records:
                    records.append(seed)
                updates = {"discovery_records": records,
                           "discovery_sources": list(dict.fromkeys([*existing.discovery_sources, seed.discovery_source]))}
                # Only fill unknown identity/location fields, never overwrite rich data.
                for field in ("name", "city", "country", "region"):
                    if not getattr(existing, field):
                        updates[field] = getattr(candidate, field)
                profile = ClinicProfile.model_validate({**existing.model_dump(), **updates})
                if profile != existing:
                    profiles[existing_id] = profile
                    snapshots.append(profile)
                    counts["merged"] += 1
                else:
                    counts["skipped"] += 1
                domains[domain] = existing_id
            else:
                profile = candidate
                profiles[profile.clinic_id] = profile
                domains[domain] = profile.clinic_id
                counts["imported"] += 1
                snapshots.append(profile)
            if _name_key(profile):
                names[_name_key(profile)] = profile.clinic_id
        except ValueError:
            counts["invalid"] += 1
    updated = ClinicIntelligenceDataset(profiles=list(profiles.values()), fits=dataset.fits, outreach_queue=dataset.outreach_queue)
    for profile in snapshots:
        publish_json(root / "data/clinics/history" / profile.clinic_id / f"{new_run_id(now)}.json", profile)
    if updated != dataset:
        publish_json(root / "data/clinics/clinics.json", updated)
    counts["total_indexed"] = len(updated.profiles)
    return counts


class ClinicIndexer:
    def __init__(self, *, root: Path, fetcher=fetch_html, now_factory=lambda: datetime.now(timezone.utc)):
        self.root, self.fetcher, self.now_factory = root, fetcher, now_factory

    def dataset(self):
        path = self.root / "data/clinics/clinics.json"
        return ClinicIntelligenceDataset.model_validate_json(path.read_text()) if path.exists() else ClinicIntelligenceDataset()

    def index(self, seeds: list[ClinicSeed], *, only_new=False, limit=25, country=None, region=None, priority=None):
        dataset = self.dataset()
        if only_new:
            known = {clinic_domain(str(item.website)) for item in dataset.profiles}
            seeds = [seed for seed in seeds if clinic_domain(str(seed.url)) not in known]
        report = []
        for seed in select_seeds(seeds, limit=limit, country=country, region=region, priority=priority):
            home = normalize_url(str(seed.url))
            existing = next((item for item in dataset.profiles if clinic_domain(str(item.website)) == clinic_domain(home)), None)
            if existing:
                report.append({"url": home, "status": "already_indexed", "clinic_id": existing.clinic_id})
                continue
            try:
                text, _ = clean_html(self.fetcher(home))
                text = text[:12000]
                extraction = DeterministicClinicExtractionClient().generate(
                    instructions="", input_text=json.dumps({"website": home, "pages": {home: text}}), output_type=ClinicExtraction)
                # Hints are candidates, not facts: accept only literal source matches.
                fields = list(extraction.fields)
                for field, hint in (("name", seed.name_hint), ("city", seed.city_hint), ("country", seed.country_hint)):
                    if hint and hint.casefold() in text.casefold():
                        fields = [item for item in fields if item.field != field]
                        match = re.search(re.escape(hint), text, flags=re.IGNORECASE)
                        literal = match.group() if match else hint
                        fields.append(SourceField(field=field, value=literal, source_url=home, source_excerpt=literal, confidence="low"))
                now = self.now_factory()
                profile = _profile_from_extraction(clinic_id_for("https://" + clinic_domain(home)), home, {home: text}, ClinicExtraction(fields=fields), now)
                # Basic indexing must not imply the detailed extractor has run.
                basic = {field: getattr(profile, field) for field in ("clinic_id", "name", "website", "city", "country", "therapies_offered", "source_urls", "last_checked_at", "confidence")}
                basic["provenance"] = [item for item in profile.provenance if item.field in basic]
                profile = ClinicProfile(**basic, profile_state="indexed", discovery_sources=[seed.discovery_source])
                duplicate = next((item for item in dataset.profiles if _name_key(profile) is not None and _name_key(item) == _name_key(profile)), None)
                if duplicate:
                    report.append({"url": home, "status": "duplicate_name_location", "clinic_id": duplicate.clinic_id})
                    continue
                fit = assess_clinic_fit(profile, now=now)
                dataset = ClinicIntelligenceDataset(profiles=[*dataset.profiles, profile], fits=[*dataset.fits, fit], outreach_queue=dataset.outreach_queue)
                publish_json(self.root / "data/clinics/history" / profile.clinic_id / f"{new_run_id(now)}.json", profile)
                publish_json(self.root / "data/clinics/clinics.json", dataset)
                report.append({"url": home, "status": "indexed", "clinic_id": profile.clinic_id})
            except (OSError, ValueError) as error:
                report.append({"url": home, "status": "skipped", "reason": str(error)})
        return report


def enrich_selected(ingestor: ClinicIngestor, seeds: list[ClinicSeed], *, limit=None, country=None, region=None, priority=None, only_new=False):
    limit = min(10, ingestor.max_clinics) if limit is None else limit
    if not 1 <= limit <= ingestor.max_clinics:
        raise ValueError("enrichment limit exceeds configured conservative batch bound")
    if priority is not None and not 1 <= priority <= 5:
        raise ValueError("priority must be between 1 and 5 (1 is highest)")
    profiles = ingestor._dataset().profiles
    seed_map = {clinic_domain(str(seed.url)): seed for seed in seeds if seed.enabled}
    selected = [profile for profile in profiles if clinic_domain(str(profile.website)) in seed_map
                and (not only_new or profile.profile_state is ClinicProfileState.INDEXED)
                and (country is None or (profile.country or "").casefold() == country.casefold())
                and (region is None or (profile.region or "").casefold() == region.casefold())
                and (priority is None or seed_map[clinic_domain(str(profile.website))].priority <= priority)]
    selected.sort(key=lambda profile: (seed_map[clinic_domain(str(profile.website))].priority, profile.clinic_id))
    return ingestor.batch([str(profile.website) for profile in selected[:limit]], refresh=True)
