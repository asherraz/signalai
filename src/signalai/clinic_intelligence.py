"""Bounded, public-source clinic ingestion; no outreach or legal conclusions."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from signalai.client import ModelClient
from signalai.schemas.clinic_intelligence import (
    ClinicConfidence, ClinicExtraction, ClinicFitAssessment, ClinicFitLevel,
    ClinicIntelligenceDataset, ClinicProfile, ClinicReviewStatus, ClinicRoute,
    ClinicTherapy, SourceField,
)
from signalai.storage import new_run_id, publish_json


FIELD_NAMES = {
    "name", "country", "city", "address", "physicians", "specialties",
    "therapies_offered", "routes_of_administration", "indications", "cell_sources",
    "exosome_or_ev_offering", "secretome_offering", "product_or_supplier_names",
    "manufacturing_or_quality_claims", "evidence_claims",
    "research_or_publication_links", "regulatory_or_licensing_claims",
    "price_information", "contact_page",
}
LIST_FIELDS = {
    "physicians", "specialties", "therapies_offered", "routes_of_administration",
    "indications", "cell_sources", "product_or_supplier_names",
    "manufacturing_or_quality_claims", "evidence_claims",
    "research_or_publication_links", "regulatory_or_licensing_claims",
    "price_information",
}
PAGE_WORDS = ("treatment", "service", "therapy", "about", "team", "physician", "doctor", "research", "science", "contact")
EXTRACTION_VERSION = "1.6"
THERAPY_MARKERS = {
    ClinicTherapy.STEM_CELLS_UNSPECIFIED: ("stem cell",),
    ClinicTherapy.AUTOLOGOUS_STEM_CELLS: ("autologous",),
    ClinicTherapy.ALLOGENEIC_STEM_CELLS: ("allogeneic",),
    ClinicTherapy.MSC: ("mesenchymal", "msc"),
    ClinicTherapy.BONE_MARROW: ("bone marrow",),
    ClinicTherapy.ADIPOSE: ("adipose",),
    ClinicTherapy.UMBILICAL_BIRTH_TISSUE: ("umbilical", "birth tissue", "cord-derived", "cord blood"),
    ClinicTherapy.EXOSOMES_EVS: ("exosome", "extracellular vesicle"),
    ClinicTherapy.SECRETOME_CONDITIONED_MEDIA: ("secretome", "conditioned media"),
    ClinicTherapy.PRP: ("prp", "platelet rich plasma", "platelet-rich plasma"),
    ClinicTherapy.PEPTIDES: ("peptide",),
    ClinicTherapy.OTHER_REGENERATIVE: ("regenerative",),
}
ROUTE_MARKERS = {
    ClinicRoute.IV: (" iv ", "intravenous", "iv care"),
    ClinicRoute.INTRA_ARTICULAR: ("intra-articular", "joint injection"),
    ClinicRoute.INTRATHECAL: ("intrathecal",),
    ClinicRoute.INTRANASAL: ("intranasal", "nasal administration"),
    ClinicRoute.LOCAL_INJECTION: ("local injection",),
    ClinicRoute.TOPICAL: ("topical",),
    ClinicRoute.OTHER: ("administration",),
}
EXTRACTION_INSTRUCTIONS = (
    "Extract only explicit public clinic facts from supplied cleaned pages. Return one "
    "ClinicExtraction object. Each field/value needs an exact supporting source URL "
    "and short verbatim excerpt from that page. Use only supplied page URLs. "
    "For therapies_offered and routes_of_administration use schema enum values. "
    "Unknown or merely implied values must be omitted. Marketing claims are claims "
    "by the clinic, not verified clinical or legal facts. No private reasoning."
)


def normalize_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("clinic URL must be a public http(s) URL without credentials")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local clinic URLs are not allowed")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("non-public clinic IP address is not allowed")
    except ValueError as exc:
        if "not allowed" in str(exc):
            raise
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", "", ""))


def _public_dns(host: str) -> None:
    for item in socket.getaddrinfo(host, None):
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise ValueError("clinic host resolves to a non-public address")


def fetch_html(url: str, *, timeout: float = 10, max_bytes: int = 1_000_000) -> str:
    """Small public-only fetch; redirects are denied before any follow-up request."""
    normalized = normalize_url(url)
    _public_dns(urlparse(normalized).hostname or "")
    request = Request(normalized, headers={"User-Agent": "SignalAIClinicIntelligence/0.1"})
    class _NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise ValueError("redirects require explicit review")

    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        kind = response.headers.get_content_type()
        if kind not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("clinic page is not HTML")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("clinic page exceeds byte limit")
        return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


class _PublicTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.skip_depth = 0
        self.anchor_href: str | None = None
        self.anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.anchor_href = dict(attrs).get("href")
            self.anchor_text = []
        if tag in {"script", "style", "noscript", "svg", "footer", "nav"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "footer", "nav"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "a" and self.anchor_href:
            if any(word in " ".join(self.anchor_text).lower() or word in self.anchor_href.lower() for word in PAGE_WORDS):
                self.links.append(self.anchor_href)
            self.anchor_href = None

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if clean:
            if self.anchor_href:
                self.anchor_text.append(clean)
            if not self.skip_depth:
                self.parts.append(clean)


def clean_html(html: str) -> tuple[str, list[str]]:
    parser = _PublicTextParser()
    parser.feed(html)
    return "\n".join(parser.parts), parser.links


def _page_text(page_url: str, html: str) -> tuple[str, list[str]]:
    text, links = clean_html(html)
    public_links = []
    for link in links:
        try:
            public_links.append(normalize_url(urljoin(page_url, link)))
        except ValueError:
            continue
    if public_links:
        text += "\n" + "\n".join(f"Link: {link}" for link in dict.fromkeys(public_links))
    return text, links


def discover_pages(home_url: str, links: list[str], limit: int) -> list[str]:
    home = normalize_url(home_url)
    host = urlparse(home).hostname
    selected = [home]
    for link in links:
        try:
            candidate = normalize_url(urljoin(home, link))
        except ValueError:
            continue
        if urlparse(candidate).hostname == host and candidate not in selected:
            selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def clinic_id_for(url: str) -> str:
    host = urlparse(normalize_url(url)).hostname or ""
    return "clinic-web-" + hashlib.sha256(host.encode()).hexdigest()[:16]


def _level(points: int) -> ClinicFitLevel:
    if points >= 5:
        return ClinicFitLevel.HIGH
    if points >= 2:
        return ClinicFitLevel.MODERATE
    if points:
        return ClinicFitLevel.LOW
    return ClinicFitLevel.UNKNOWN


def assess_clinic_fit(profile: ClinicProfile, *, now: datetime) -> ClinicFitAssessment:
    """Transparent ordinal signals only; jurisdiction eligibility is never inferred."""
    therapies = set(profile.therapies_offered)
    text = " ".join([*profile.indications, *profile.specialties]).lower()
    neuro = any(word in text for word in ("neuro", "cognit", "brain", "longevity", "aging"))
    ev = ClinicTherapy.EXOSOMES_EVS in therapies or profile.exosome_or_ev_offering is True
    regenerative = bool(therapies.intersection({ClinicTherapy.STEM_CELLS_UNSPECIFIED, ClinicTherapy.AUTOLOGOUS_STEM_CELLS, ClinicTherapy.ALLOGENEIC_STEM_CELLS, ClinicTherapy.MSC, ClinicTherapy.EXOSOMES_EVS, ClinicTherapy.SECRETOME_CONDITIONED_MEDIA}))
    research = bool(profile.research_or_publication_links)
    technical = bool(profile.manufacturing_or_quality_claims or profile.product_or_supplier_names)
    nasal = ClinicRoute.INTRANASAL in profile.routes_of_administration
    infrastructure = any(route in profile.routes_of_administration for route in (ClinicRoute.IV, ClinicRoute.INTRA_ARTICULAR, ClinicRoute.INTRATHECAL))
    willingness = any("research" in str(item.source_url).lower() or "collaborat" in item.source_excerpt.lower() for item in profile.provenance)
    reasons = [label for flag, label in ((regenerative, "Publicly described regenerative therapies"), (ev, "EV/exosome offering"), (neuro, "Neuro/cognitive/longevity relevance"), (nasal, "Intranasal route described"), (research, "Public research links"), (technical, "Product or quality detail"), (infrastructure, "Advanced administration infrastructure indicated"), (willingness, "Public research/collaboration signal")) if flag]
    return ClinicFitAssessment(
        clinic_id=profile.clinic_id,
        regenerative_medicine_fit=_level((3 if regenerative else 0) + (2 if ev else 0) + (1 if infrastructure else 0)),
        sgl001_relevance=_level((2 if neuro else 0) + (2 if ev else 0) + (2 if nasal else 0) + (1 if research else 0)),
        advisory_partner_fit=_level((2 if research else 0) + (2 if neuro else 0) + (1 if technical else 0) + (1 if willingness else 0)),
        evaluation_site_fit=_level((2 if infrastructure else 0) + (2 if research else 0) + (1 if nasal else 0)),
        outreach_priority=_level((2 if regenerative else 0) + (2 if ev else 0) + (1 if neuro else 0) + (1 if willingness else 0)),
        rationale=reasons or ["Insufficient public detail for fit assessment"],
        assessed_at=now,
    )


def _profile_from_extraction(clinic_id: str, website: str, pages: dict[str, str], extraction: ClinicExtraction, now: datetime) -> ClinicProfile:
    values: dict[str, object] = {key: [] for key in LIST_FIELDS}
    accepted: list[SourceField] = []
    for item in extraction.fields:
        if item.field not in FIELD_NAMES:
            raise ValueError(f"unsupported extracted clinic field: {item.field}")
        page = pages.get(normalize_url(str(item.source_url)))
        if page is None or " ".join(item.source_excerpt.split()).casefold() not in " ".join(page.split()).casefold():
            raise ValueError(f"unverified source excerpt for {item.field}")
        value = item.value
        if item.field in {"therapies_offered", "routes_of_administration"}:
            value = (ClinicTherapy if item.field == "therapies_offered" else ClinicRoute)(value)
            markers = THERAPY_MARKERS[value] if item.field == "therapies_offered" else ROUTE_MARKERS[value]
            excerpt = f" {item.source_excerpt.lower()} "
            if not any(marker in excerpt for marker in markers):
                raise ValueError(f"source excerpt does not support {item.field} value {value}")
        elif isinstance(value, str) and value.casefold() not in item.source_excerpt.casefold():
            raise ValueError(f"source excerpt does not contain {item.field} value")
        if item.field in {"exosome_or_ev_offering", "secretome_offering"} and not isinstance(value, bool):
            raise ValueError("offering value must be true or false, not inferred text")
        if item.field == "exosome_or_ev_offering" and value is True and not any(marker in item.source_excerpt.lower() for marker in THERAPY_MARKERS[ClinicTherapy.EXOSOMES_EVS]):
            raise ValueError("source excerpt does not support EV offering")
        if item.field == "secretome_offering" and value is True and not any(marker in item.source_excerpt.lower() for marker in THERAPY_MARKERS[ClinicTherapy.SECRETOME_CONDITIONED_MEDIA]):
            raise ValueError("source excerpt does not support secretome offering")
        if item.field in {"exosome_or_ev_offering", "secretome_offering"} and value is False:
            excerpt = item.source_excerpt.lower()
            if not any(marker in excerpt for marker in ("do not offer", "does not offer", "not offered", "no exosome", "no ev", "no secretome")):
                raise ValueError("negative offering requires an explicit negative public statement")
        if item.field in LIST_FIELDS:
            current = values[item.field]
            assert isinstance(current, list)
            if value not in current:
                current.append(value)
        else:
            if item.field in values and values[item.field] != value:
                raise ValueError(f"conflicting extracted value for {item.field}")
            values[item.field] = value
        accepted.append(item)
    return ClinicProfile(
        clinic_id=clinic_id, website=website, source_urls=list(pages), provenance=accepted,
        last_checked_at=now, confidence=(ClinicConfidence.LOW if accepted and all(item.confidence is ClinicConfidence.LOW for item in accepted) else ClinicConfidence.MODERATE) if accepted else ClinicConfidence.UNKNOWN,
        review_status=ClinicReviewStatus.UNREVIEWED, **values,
    )


class DeterministicClinicExtractionClient:
    """No-API, low-recall fallback: emit only literal page text with traceable excerpts."""

    def __init__(self) -> None:
        self.usage_records: list[dict[str, object]] = []

    def generate(self, *, instructions: str, input_text: str, output_type: type[ClinicExtraction]) -> ClinicExtraction:
        if output_type is not ClinicExtraction:
            raise ValueError("deterministic clinic client supports only ClinicExtraction")
        self.usage_records.append({"model": "deterministic", "input_tokens": 0,
                                   "output_tokens": 0, "estimated_api_cost_usd": 0.0})
        supplied = json.loads(input_text)
        pages = supplied["pages"]
        home = supplied["website"]
        fields: list[SourceField] = []
        seen: set[tuple[str, str]] = set()

        def add(field: str, value: str | bool, url: str, excerpt: str) -> None:
            marker = (field, str(value))
            if marker not in seen:
                fields.append(SourceField(field=field, value=value, source_url=url,
                                          source_excerpt=excerpt[:350], confidence=ClinicConfidence.LOW))
                seen.add(marker)

        for url, text in pages.items():
            title = text.splitlines()[0] if text else ""
            title_parts = [part.strip() for part in re.split(r"\s+[—|–-]\s+", title)]
            names = [part for part in title_parts if len(part) <= 45 and ("clinic" in part.lower() or "center" in part.lower())]
            host_parts = (urlparse(home).hostname or "").lower().split(".")
            host_key = re.sub(r"[^a-z0-9]", "", host_parts[1] if host_parts[0] == "www" else host_parts[0])
            def key(value: str) -> str:
                plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
                return re.sub(r"[^a-z0-9]", "", plain)
            name_part = names[-1] if names else title if len(title) <= 30 and "therapy" not in title.lower() else ""
            if not name_part and url == home:
                name_part = next((part for part in reversed(title_parts) if len(key(part)) >= 5 and host_key.startswith(key(part))), "")
            if not name_part and url == home:
                name_part = next((line for line in text.splitlines()[:60] if 5 <= len(line) <= 45 and key(line) == host_key), "")
            if not name_part and url == home:
                name_part = next((match.group(1) for line in text.splitlines()[:80]
                                  if (match := re.fullmatch(r"About ([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})", line))
                                  and match.group(1).lower() not in {"stem cells", "regenerative medicine"}), "")
            if url == home and name_part:
                add("name", name_part, url, title if name_part.casefold() in title.casefold() else name_part)
            for line in text.splitlines():
                lower = line.lower()
                if len(line) > 350 or not line.strip():
                    continue
                educational = any(word in lower for word in ("guidance", "written and reviewed", "explore the dedicated guides", "about autologous", "what is regenerative", "panama center", "evaluation center"))
                offering = not educational and any(word in lower for word in ("we offer", "we provide", "we specialize", "personalized care including", "our services", "service catalog", "our clinic", "at our clinic", "directing this clinic", "this physician performs", "stem cell treatment and", "stem cell therapy and", "therapy protocols"))
                if offering:
                    for therapy, markers in THERAPY_MARKERS.items():
                        if therapy is ClinicTherapy.OTHER_REGENERATIVE or (therapy is ClinicTherapy.UMBILICAL_BIRTH_TISSUE and "conditioned serum" in lower):
                            continue
                        if any(marker in lower for marker in markers):
                            add("therapies_offered", therapy.value, url, line)
                            if therapy is ClinicTherapy.EXOSOMES_EVS:
                                add("exosome_or_ev_offering", True, url, line)
                            if therapy is ClinicTherapy.SECRETOME_CONDITIONED_MEDIA:
                                add("secretome_offering", True, url, line)
                    for route, markers in ROUTE_MARKERS.items():
                        if route is ClinicRoute.OTHER:
                            continue
                        if any(marker in f" {lower} " for marker in markers):
                            add("routes_of_administration", route.value, url, line)
                    if "stem cell" in lower or "msc" in lower:
                        for source in ("bone marrow", "adipose", "umbilical", "birth tissue", "cord blood"):
                            if source in lower:
                                add("cell_sources", source, url, line)
                    for indication in ("knee pain", "arthritis", "neuropathy", "back pain", "cognitive function", "cognitive wellness", "longevity", "anti-aging"):
                        if indication in lower:
                            add("indications", indication, url, line)
                if "$" in line and any(word in lower for word in ("consultation", "price", "cost", "plan", "treatment")):
                    for price in re.findall(r"\$\s?\d[\d,]*(?:\.\d{2})?", line):
                        add("price_information", price, url, line)
                for doctor in re.findall(r"Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}", line):
                    if re.search(re.escape(doctor) + r"\s*,?\s*(?:MD|M\.D\.|DO|D\.O\.)\b", line):
                        add("physicians", doctor, url, line)
                if "orlando, florida" in lower:
                    add("city", line[lower.index("orlando, florida"):][:7], url, line)
                if "tokyo" in lower and any(word in lower for word in ("address", "located", "clinic is", "ginza")):
                    add("city", line[lower.index("tokyo"):][:5], url, line)
                if "united states" in lower and any(word in lower for word in ("address", "located", "clinic is")):
                    add("country", line[lower.index("united states"):][:13], url, line)
                if "japan" in lower and any(word in lower for word in ("address", "located", "clinic is")):
                    add("country", line[lower.index("japan"):][:5], url, line)
                if line.startswith("Link: ") and "research" in lower:
                    add("research_or_publication_links", line[6:], url, line)
                for specialty in ("orthopedic", "neurology", "regenerative medicine", "sports medicine"):
                    if specialty in lower and not any(word in lower for word in ("central to", "worked alongside", "working alongside", "helped develop")) and any(word in lower for word in ("specialize", "physician-led", "leading expert", "our clinic")):
                        add("specialties", specialty, url, line)
        return ClinicExtraction(fields=fields)


class ClinicIngestor:
    def __init__(self, *, root: Path, client: ModelClient, fetcher: Callable[[str], str] = fetch_html,
                 max_pages: int = 5, max_clinics: int = 5, max_page_chars: int = 12_000,
                 now_factory=lambda: datetime.now(timezone.utc)) -> None:
        if not 1 <= max_pages <= 10 or not 1 <= max_clinics <= 10 or max_page_chars < 100:
            raise ValueError("clinic ingestion bounds must be conservative")
        self.root, self.client, self.fetcher = root, client, fetcher
        self.max_pages, self.max_clinics, self.max_page_chars = max_pages, max_clinics, max_page_chars
        self.now_factory = now_factory
        self.last_skipped_pages: list[dict[str, str]] = []
        self.batch_report: list[dict[str, object]] = []

    def _dataset(self) -> ClinicIntelligenceDataset:
        path = self.root / "data/clinics/clinics.json"
        return ClinicIntelligenceDataset.model_validate_json(path.read_text()) if path.exists() else ClinicIntelligenceDataset()

    def ingest(self, url: str, *, refresh: bool = False) -> tuple[ClinicProfile, ClinicFitAssessment, bool]:
        self.last_skipped_pages = []
        home = normalize_url(url)
        clinic_id = clinic_id_for(home)
        dataset = self._dataset()
        existing = next((item for item in dataset.profiles if item.clinic_id == clinic_id), None)
        cache_path = self.root / "data/clinics/cache" / f"{clinic_id}.json"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else None
        if existing and cache and not refresh and cache.get("extraction_version") == EXTRACTION_VERSION:
            fit = next(item for item in dataset.fits if item.clinic_id == clinic_id)
            return existing, fit, False
        if existing and cache and not refresh:
            pages = cache["pages"]
            fingerprint = cache["fingerprint"]
        else:
            raw_home = self.fetcher(home)
            home_text, links = _page_text(home, raw_home)
            page_urls = discover_pages(home, links, self.max_pages)
            pages = {home: home_text[:self.max_page_chars]}
            for page_url in page_urls[1:]:
                try:
                    text, _ = _page_text(page_url, self.fetcher(page_url))
                except (OSError, ValueError) as exc:
                    self.last_skipped_pages.append({"url": page_url, "reason": f"{type(exc).__name__}: {exc}"})
                    continue
                pages[page_url] = text[:self.max_page_chars]
            fingerprint = hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest()
        if existing and cache and cache.get("fingerprint") == fingerprint and cache.get("extraction_version") == EXTRACTION_VERSION:
            return existing, next(item for item in dataset.fits if item.clinic_id == clinic_id), False
        usage_start = len(getattr(self.client, "usage_records", []))
        extraction = self.client.generate(
            instructions=EXTRACTION_INSTRUCTIONS,
            input_text=json.dumps({"website": home, "pages": pages}, sort_keys=True),
            output_type=ClinicExtraction,
        )
        now = self.now_factory()
        profile = _profile_from_extraction(clinic_id, home, pages, extraction, now)
        fit = assess_clinic_fit(profile, now=now)
        updated = ClinicIntelligenceDataset(
            profiles=[item for item in dataset.profiles if item.clinic_id != clinic_id] + [profile],
            fits=[item for item in dataset.fits if item.clinic_id != clinic_id] + [fit],
            outreach_queue=dataset.outreach_queue,
        )
        run_id = new_run_id(now)
        history = self.root / "data/clinics/history" / clinic_id / f"{run_id}.json"
        history.parent.mkdir(parents=True, exist_ok=True)
        publish_json(history, profile)
        publish_json(self.root / "data/clinics/clinics.json", updated)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"fingerprint": fingerprint, "extraction_version": EXTRACTION_VERSION, "pages": pages}, indent=2) + "\n")
        usage = getattr(self.client, "usage_records", [])[usage_start:]
        private = self.root / "data/clinics/private-runs" / f"{run_id}.json"
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text(json.dumps({"clinic_id": clinic_id, "pages_fetched": len(pages), "usage": usage}, indent=2) + "\n")
        return profile, fit, True

    def batch(self, urls: list[str], *, refresh: bool = False) -> list[tuple[ClinicProfile, ClinicFitAssessment, bool]]:
        if len(urls) > self.max_clinics:
            raise ValueError("clinic batch exceeds configured limit")
        self.batch_report = []
        results = []
        for url in dict.fromkeys(urls):
            usage_start = len(getattr(self.client, "usage_records", []))
            try:
                profile, fit, changed = self.ingest(url, refresh=refresh)
                results.append((profile, fit, changed))
                usage = getattr(self.client, "usage_records", [])[usage_start:]
                self.batch_report.append({"url": url, "status": "indexed" if changed else "unchanged", "clinic_id": profile.clinic_id, "pages_skipped": self.last_skipped_pages, "estimated_api_cost_usd": sum(item.get("estimated_api_cost_usd") or 0 for item in usage) if usage else None})
            except Exception as exc:
                usage = getattr(self.client, "usage_records", [])[usage_start:]
                self.batch_report.append({"url": url, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "pages_skipped": self.last_skipped_pages, "estimated_api_cost_usd": sum(item.get("estimated_api_cost_usd") or 0 for item in usage) if usage else None})
        return results
