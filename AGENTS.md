# SignalAI Engineering Guide

## Mission and boundaries

Build SignalAI as a clean-room, OpenAI-native Python system for therapeutic
asset development. SGL-001 is the first program. Do not copy architecture or
code from the older `signalAgent` repository. Do not add Anthropic or Claude
dependencies, configuration, prompts, or terminology.

The current repository phase is foundational. Do not implement autonomous
agents, scientific retrieval, web research, scheduled workflows, or frontend
code unless a later task explicitly authorizes it.

## Architectural rules

- Use Python for the core runtime and the official OpenAI SDK for future model
  inference.
- Use strict Pydantic models and structured JSON for canonical scientific state.
- Use Markdown only for human-readable generated reports.
- Give every persisted entity a stable ID and every execution a unique run ID.
- Preserve run inputs, intermediate outputs, checkpoints, errors, and results.
- Preserve evidence provenance for every scientific claim. Never silently turn
  an unsupported assertion into canonical state.
- Model major therapeutic-development decisions as human-approval gates.
- Keep internal state separate from generated, sanitized public JSON.
- Keep model orchestration in `agents/`, bounded integrations in `tools/`, and
  data contracts in `schemas/`.

## Scientific integrity

Do not fabricate citations, measurements, experimental results, or regulatory
facts. Distinguish evidence, inference, hypothesis, and decision. Retain source
identifiers and locator details sufficient for an auditor to trace a claim back
to its source.

## Engineering workflow

- Prefer small, typed modules and explicit interfaces.
- Add or update tests whenever schemas or behavior change.
- Keep secrets out of Git; document environment variables in `.env.example`.
- Do not commit generated caches, virtual environments, or `.env` files.
- Run the relevant tests before handing work back.
- Do not commit or push unless the user explicitly asks.
