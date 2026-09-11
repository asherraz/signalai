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

## Data conventions

- Canonical machine state is JSON validated by Pydantic.
- Human-facing output is Markdown.
- Timestamps must include a timezone and are normalized to UTC.
- Persistent entities use stable IDs; every run uses a unique `run_id`.
- Claims must cite at least one evidence record.
- Approval-gated decisions are not approved until a human identity and approval
  timestamp are recorded.
