# SignalAI

SignalAI is an AI-native system for developing therapeutic assets. Its first
development program is SGL-001, an intranasal extracellular-vesicle/exosome
therapeutic program.

This repository is a clean-room implementation. It is Python- and OpenAI-native
and does not use Anthropic or Claude dependencies.

## Current scope

Milestone 1 provides a minimal sequential therapeutic-development run over local
fixture evidence. Four bounded roles extract claims, propose a hypothesis,
critique it, and produce a decision proposal that remains pending human
approval. It deliberately does **not** implement PubMed or web retrieval,
scheduled workflows, or frontend code.

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

The records in `evidence/fixtures/sgl-001.json` are synthetic, testing-only
examples. They are not scientific sources and must not be used to support real
therapeutic-development decisions.

## Data conventions

- Canonical machine state is JSON validated by Pydantic.
- Human-facing output is Markdown.
- Timestamps must include a timezone and are normalized to UTC.
- Persistent entities use stable IDs; every run uses a unique `run_id`.
- Claims must cite at least one evidence record.
- Approval-gated decisions are not approved until a human identity and approval
  timestamp are recorded.
