# SignalAI

SignalAI is an AI-native system for developing therapeutic assets. Its first
development program is SGL-001, an intranasal extracellular-vesicle/exosome
therapeutic program.

This repository is a clean-room implementation. It is Python- and OpenAI-native
and does not use Anthropic or Claude dependencies.

## Current scope

The current milestone provides a minimal sequential therapeutic-development run
over curated local evidence. Four bounded roles extract claims, propose a
hypothesis, critique it and identify risks, and produce a decision proposal that
remains pending human approval. It deliberately does **not** implement PubMed or
web retrieval, scheduled workflows, or frontend code.

## Architecture

- `src/signalai/schemas/`: strict, versionable scientific and operational data
  contracts. Records refer to one another by stable IDs so they can be stored,
  audited, and evolved independently.
- `src/signalai/agents/`: bounded role instructions used by the orchestrator.
- `src/signalai/tools/`: future bounded integrations used by agents. No
  retrieval tools are implemented yet.
- `state/`: canonical internal scientific state as structured JSON.
- `evidence/`: evidence records and source artifacts with provenance.
- `runs/`: durable per-run inputs, checkpoints, intermediate outputs, errors,
  and final manifests. Every future run must use a unique run ID.
- `reports/`: human-readable Markdown outputs.
- `public/`: generated, sanitized JSON for the separate frontend.
- `evals/`: evaluation cases and fixtures for later agent behavior.
- `tests/`: schema and runtime tests.

The intended data flow is evidence -> typed scientific records -> reviewed
decisions -> generated public state. Scientific claims retain evidence IDs;
major decisions expose an explicit human-approval state. Run artifacts are
file-backed so interrupted workflows can later resume without discarding
intermediate work.

## Development

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Copy `.env.example` to `.env` and never commit API keys. Set `OPENAI_API_KEY` and
`OPENAI_MODEL`, then run from the repository root:

```bash
signalai-run
```

The command uses the official OpenAI Python SDK and Responses API. It creates a
unique directory under `runs/`, persists each validated stage with create-only
writes, and atomically updates `public/signal-state.json` after successful final
validation.

## Daily autonomy

`state/development-agenda.json` is the persistent, typed backlog of scientific
questions, hypotheses, translational risks, formulation questions, experiment
proposals, pending decisions, and evidence gaps. A daily run selects exactly one
open item using therapeutic-development value rather than novelty:

```bash
signalai-daily-run
```

The daily cycle reads `state/signal-state.json` and the agenda, records task
selection, analysis, critique, synthesis, updated state, updated agenda, and a
concise change entry under a unique run directory, then publishes the validated
public state. It may record `no material scientific change`; major decisions
remain pending human approval.

The live intelligence path adds a typed docket at
`state/development-docket.json`. It deterministically chooses one highest-value
matter, convenes relevant domain reviewers plus independent Verifier, Adversary,
and Chair roles, and publishes only after the entire bounded run validates:

```bash
python -m signalai daily
```

`OPENAI_REASONING_EFFORT` controls the economical default and
`OPENAI_CHAIR_REASONING_EFFORT` can reserve stronger reasoning for the chair.
Chair serialization uses a separate bounded allowance and one repair attempt,
configured by `OPENAI_CHAIR_MAX_OUTPUT_TOKENS` and
`OPENAI_CHAIR_RETRY_MAX_OUTPUT_TOKENS`; earlier reviewers are not repeated.
The Chair returns findings and proposed changes but does not classify its own
lifecycle result. Deterministic code normalizes no-ops and separates editorial,
operational, scientific-state, decision, and human-approval outcomes using a
discriminated determination contract.
Returned token totals and estimated cost are retained only in private run artifacts. The daily
GitHub workflow supports manual dispatch, commits only successful runs, and
suppresses timestamp-only commits.

## SignalRB — Signal Review Board

Unsupported analysis is an expected review outcome, not an infrastructure error.
The live runner allows at most one shared analysis-only repair (including citation
repair), before independent verification. Valid but still insufficient evidence
produces a typed `evidence_gap` determination: all proposed scientific, decision,
and operational changes are rejected, prior program JSON is preserved byte-for-byte,
and the unresolved matter stays open. The completed run publishes a concise gap
explanation and evidence/citation next action. Exact unsupported conclusions and
rejected proposals are retained only in private run artifacts. Public reviewer
entries are explicitly marked unsupported rather than presented as accepted facts.
SignalRB records `previous_state_preserved: true` for this outcome. API/network
errors, malformed structured output after repair, invalid references, and corrupted
canonical state still abort without publication and cause a non-zero daily exit.

`flagshipProgram` is a deterministic, typed public view of SGL-001 as the
flagship program of Signal Intelligence. It derives its thesis, blockers, six
development gates, linked determination, and chronological history from canonical
program state and SignalRB. Gate categories use inspectable keyword mapping in
`flagship_export.py`; a recorded product hypothesis is only `partially_defined`,
an open high/critical risk is `blocked`, and the latest relevant operator gate is
`human_decision`. Literature support never implies asset-gate completion.
Unassessed gates remain `unresolved`; absent next actions are JSON null.
Pivot criteria retain only recorded failure/weakening conditions, with review
and evidence references. No synthetic-chassis or cargo pivot threshold is added
without a source record. Summaries use sourced sentences and preserve qualifiers;
`updatedAt` is a source timestamp, not a publication timestamp.

`signalRB` is the canonical public review/determination layer. Its typed
`SignalReviewBoardDetermination` objects derive from completed live runs and
validated analysis, independent verification, and adversary artifacts. Supporting
domains remain separate; reviews reference canonical evidence IDs rather than
copying datasets. Review history is newest-first and deduplicated by run ID.
Pending decisions omit private approver/contact metadata. This export does not
alter scientific state or approval gates.

The deprecated `aiRB` projection and stable `airb` module/feed identifiers remain
for existing consumers. Historical `aiRB`, `airb`, and `aiRB determination` payload
keys load through an adapter when `signalRB` is absent. Missing historical detail
is explicitly `not_recorded`; immutable run artifacts are never rewritten.

## Clinic intelligence

Public-source clinic profiles are separate from the human-approved Clinical
Network partner records. `data/clinics/clinics.json` holds typed, field-sourced
profiles and ordinal SGL-001 fit assessments. An indexed clinic is **not** an
approved partner, and fit does not establish legal eligibility or clinical
readiness. `public/signal-state.json` exposes a sanitized `clinicIntelligence`
summary; private outreach, page caches, and API usage are excluded.

```bash
python -m signalai clinic-ingest https://clinic.example/
python -m signalai clinic-batch path/to/clinic-urls.txt
python -m signalai clinic-scheduled
```

The scheduled mode is an opt-in command, not part of the SGL-001 daily workflow.
It processes a small manually supplied `data/clinics/queue.txt` and stale
profiles, up to six clinics and five same-site pages each by default. It does
not discover sites broadly or send outreach. Cached pages skip unchanged model
calls; immutable profile snapshots preserve history. The extraction call uses
`OPENAI_CLINIC_MODEL` (default `gpt-5-mini`) and low reasoning. Every accepted
field must cite a fetched URL and matching excerpt; unsupported values remain
unknown. When no local `OPENAI_API_KEY` is available, the command uses a
conservative deterministic extractor with lower recall and zero API cost.
Outreach candidates require human approval before any action.

## Therapeutic asset workspace

`state/asset-development.json` is the canonical biology-to-product-to-market
workspace for SGL-001. It keeps three typed domains alongside, rather than
inside, the scientific claim state:

- Cargo maps operator-selected payload strategy, evidence-ranked benchmarks,
  biological pathways, and candidate-to-pathway convergence.
- Formulation compares product configurations with inspectable ordinal scores
  and represents the excipient design space without inventing concentrations or
  compatibility evidence.
- Jurisdictions records regulator-sourced market-entry assessments, keeps legal
  viability separate from enforcement intensity, and requires human-reviewed
  next actions before clinic planning.

Each domain links back to canonical hypotheses, risks, decisions, and agenda
items. The public serializer publishes sanitized `cargo`, `formulation`, and
`jurisdictions` projections for the separate frontend while detailed source and
legal-framework records remain internal.

Legacy JSON can be migrated through an explicit read-only adapter:

```bash
SIGNALAI_LEGACY_ROOT=/Users/raziel/Desktop/signalAgent signalai-migrate-legacy
```

The importer validates all output, retains source paths and SHA-256 hashes,
preserves original formulation scores alongside uncalibrated ordinal mappings,
marks legacy jurisdiction conclusions as unverified, writes
`reports/legacy-import-report.json`, and regenerates the public workspace.

The records in `evidence/fixtures/sgl-001.json` are curated, local summaries of
traceable publications. They support planning and software validation, not
clinical conclusions. The current evidence is preclinical or methodological and
does not establish human efficacy for SGL-001.

## Global clinic index

Indexed clinics, reviewed clinics, and approved Signal partners are distinct.
`profile_state` is `indexed` for a sourced basic record or `enriched` after the
detailed extractor runs. Neither state changes review or partnership approval.
Historical detailed records default to `enriched` when loaded.

`data/clinic-seeds.json` is the canonical 100-clinic discovery dataset. `website`
loads through the existing `url` alias. Seed records retain name/location hints,
region, source URL, discovery date, category hint and untrusted discovery-status
annotations. The CSV is a backup only; the summary validates exactly 100 rows
with 50 Asia / 25 United States / 25 Rest of World before bulk import.
Discovery identity/location metadata is distinct from verified page claims.
Existing URL-only JSON/text lists remain supported for discovery tools.

```bash
python -m signalai clinic-discover directory-export.json --limit 1000
python -m signalai clinic-import data/clinic-seeds.json
python -m signalai clinic-index --limit 25 --only-new
python -m signalai clinic-index --country Japan --priority 2 --limit 10
python -m signalai clinic-enrich --limit 10 --region Asia --only-new
```

Discovery imports supplied directory exports in the seed schema or manual URL
lists; it does not recursively crawl directories or search for arbitrary sites.
Bulk import uses zero fetches and zero model calls, preserving each seed as
discovery provenance. It merges matching domains or exact name/location pairs,
fills only missing identity/location metadata, and never replaces richer facts.
Existing clinics outside the 100-seed set remain in the index. Re-import is
idempotent. The separate website-checking index path uses one bounded HTML fetch
per selected domain and zero model calls.
It requires a sourced name and explicit stem-cell/cell-derived therapy offering;
insufficient pages are skipped rather than converted into fabricated profiles.
HTTP/HTTPS and `www` aliases deduplicate by domain. Exact names deduplicate only
when both city and country agree; ambiguous same-name clinics remain separate.
Enrichment targets existing indexed records (or refreshes detailed records when
`--only-new` is absent), preserving IDs and immutable profile snapshots. It uses
the existing conservative page/model budgets. No outreach or legality inference
is performed.

Discovery, website indexing and enrichment support `--limit`, `--country`,
`--region`, and `--priority`. Bulk import always validates/imports the full
canonical dataset. Enrichment defaults to at most 10 clinics and 5 same-site
pages, with unchanged cached text skipping model extraction.
`--only-new` skips existing domains during indexing and enriched profiles during
enrichment. Discovery is inherently additive and never replaces existing seeds.
Country filters use supplied country hints for discovery/index selection and
profile discovery/sourced identity for enrichment; unknown countries do not
match. Indexed public cards expose only identity, location, and profile status
(plus stable IDs). Detailed fields and fit signals are exposed only for enriched
cards. Therapy counts use enriched records, not seed categories. Region/country
counts include explicitly labeled discovery locations. Private diagnostics,
costs, outreach notes and discovery verification annotations are not exported.

## Data conventions

- Canonical machine state is JSON validated by Pydantic.
- Human-facing output is Markdown.
- Timestamps must include a timezone and are normalized to UTC.
- Persistent entities use stable IDs; every run uses a unique `run_id`.
- Claims must cite at least one evidence record.
- Approval-gated decisions are not approved until a human identity and approval
  timestamp are recorded.
