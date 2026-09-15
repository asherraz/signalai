"""Public projection excludes internal outreach, usage, cache, and provenance excerpts."""

from collections import Counter

from signalai.schemas.clinic_intelligence import ClinicFitLevel, ClinicIntelligenceDataset, ClinicTherapy
from signalai.schemas.public_clinic_intelligence import (
    PublicBasicClinic, PublicClinicIntelligence, PublicClinicIntelligenceSummary, PublicIndexedClinic,
)


def export_clinic_intelligence(dataset: ClinicIntelligenceDataset) -> PublicClinicIntelligence:
    fits = {item.clinic_id: item for item in dataset.fits}
    cards = []
    for profile in dataset.profiles:
        if profile.profile_state.value == "indexed":
            cards.append(PublicBasicClinic(clinicId=profile.clinic_id, name=profile.name,
                website=str(profile.website), city=profile.city, country=profile.country,
                region=profile.region, profileState="indexed"))
            continue
        fit = fits.get(profile.clinic_id)
        cards.append(PublicIndexedClinic(
            clinicId=profile.clinic_id,
            name=profile.name,
            website=str(profile.website),
            profileState=profile.profile_state.value,
            country=profile.country,
            city=profile.city,
            region=profile.region,
            therapiesOffered=profile.therapies_offered,
            routesOfAdministration=profile.routes_of_administration,
            indications=profile.indications,
            exosomeOrEvOffering=profile.exosome_or_ev_offering,
            confidence=profile.confidence.value,
            reviewStatus=profile.review_status.value,
            sourceUrls=[str(url) for url in profile.source_urls],
            lastCheckedAt=profile.last_checked_at,
            sgl001Relevance=fit.sgl001_relevance if fit else ClinicFitLevel.UNKNOWN,
            outreachPriority=fit.outreach_priority if fit else ClinicFitLevel.UNKNOWN,
        ))
    cards.sort(key=lambda item: item.clinic_id)
    detailed = [item for item in cards if isinstance(item, PublicIndexedClinic)]
    top = [item for item in detailed if item.sgl001_relevance is ClinicFitLevel.HIGH]
    checked = {profile.clinic_id: profile.last_checked_at for profile in dataset.profiles}
    recent = sorted(cards, key=lambda item: checked[item.clinic_id], reverse=True)[:5]
    return PublicClinicIntelligence(
        summary=PublicClinicIntelligenceSummary(
            clinicsIndexed=len(cards),
            clinicsEnriched=sum(item.profile_state == "enriched" for item in cards),
            stemCellClinics=sum(bool(set(item.therapies_offered).intersection(set(ClinicTherapy) - {ClinicTherapy.EXOSOMES_EVS, ClinicTherapy.SECRETOME_CONDITIONED_MEDIA, ClinicTherapy.PRP, ClinicTherapy.PEPTIDES, ClinicTherapy.OTHER_REGENERATIVE})) for item in detailed),
            clinicsByCountry=dict(sorted(Counter(item.country for item in cards if item.country).items())),
            clinicsByRegion=dict(sorted(Counter(item.region for item in cards if item.region).items())),
            clinicsByTherapy=dict(sorted(Counter(therapy.value for item in detailed for therapy in set(item.therapies_offered)).items())),
            countries=len({item.country for item in cards if item.country}),
            exosomeClinics=sum(
                item.exosome_or_ev_offering is True or ClinicTherapy.EXOSOMES_EVS in item.therapies_offered
                for item in detailed
            ),
            neuroRelevantClinics=sum(item.sgl001_relevance in {ClinicFitLevel.MODERATE, ClinicFitLevel.HIGH} for item in detailed),
        ),
        clinics=cards,
        topMatches=top,
        recentlyIndexed=recent,
    )
