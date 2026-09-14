"""Public projection excludes internal outreach, usage, cache, and provenance excerpts."""

from signalai.schemas.clinic_intelligence import ClinicFitLevel, ClinicIntelligenceDataset, ClinicTherapy
from signalai.schemas.public_clinic_intelligence import (
    PublicClinicIntelligence, PublicClinicIntelligenceSummary, PublicIndexedClinic,
)


def export_clinic_intelligence(dataset: ClinicIntelligenceDataset) -> PublicClinicIntelligence:
    fits = {item.clinic_id: item for item in dataset.fits}
    cards = []
    for profile in dataset.profiles:
        fit = fits[profile.clinic_id]
        cards.append(PublicIndexedClinic(
            clinicId=profile.clinic_id,
            name=profile.name,
            website=str(profile.website),
            country=profile.country,
            city=profile.city,
            therapiesOffered=profile.therapies_offered,
            routesOfAdministration=profile.routes_of_administration,
            indications=profile.indications,
            exosomeOrEvOffering=profile.exosome_or_ev_offering,
            confidence=profile.confidence.value,
            reviewStatus=profile.review_status.value,
            sourceUrls=[str(url) for url in profile.source_urls],
            lastCheckedAt=profile.last_checked_at,
            sgl001Relevance=fit.sgl001_relevance,
            outreachPriority=fit.outreach_priority,
        ))
    cards.sort(key=lambda item: item.clinic_id)
    top = [item for item in cards if item.sgl001_relevance is ClinicFitLevel.HIGH]
    recent = sorted(cards, key=lambda item: item.last_checked_at, reverse=True)[:5]
    return PublicClinicIntelligence(
        summary=PublicClinicIntelligenceSummary(
            clinicsIndexed=len(cards),
            countries=len({item.country for item in cards if item.country}),
            exosomeClinics=sum(
                item.exosome_or_ev_offering is True or ClinicTherapy.EXOSOMES_EVS in item.therapies_offered
                for item in cards
            ),
            neuroRelevantClinics=sum(item.sgl001_relevance in {ClinicFitLevel.MODERATE, ClinicFitLevel.HIGH} for item in cards),
        ),
        clinics=cards,
        topMatches=top,
        recentlyIndexed=recent,
    )
