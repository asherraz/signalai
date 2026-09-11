"""Typed OpenAI Responses API boundary with bounded structured-output recovery."""

from __future__ import annotations

import json
from os import environ
from typing import Any, Protocol, TypeVar, cast

import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError


OutputT = TypeVar("OutputT", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    """Safe base error for an unusable typed model response."""


class IncompleteResponseError(StructuredOutputError):
    """The Responses API explicitly reported incomplete generation."""


class MalformedStructuredOutputError(StructuredOutputError):
    """The response completed but could not be parsed into the requested schema."""


class ModelClient(Protocol):
    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT: ...


def _nested_int(value: Any, *path: str) -> int:
    for field in path:
        value = getattr(value, field, None) if not isinstance(value, dict) else value.get(field)
        if value is None:
            return 0
    return int(value)


class OpenAIResponsesClient:
    """Generate validated Pydantic outputs and retain private usage summaries."""

    _DEFAULT_PRICING = {
        "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.0}
    }

    def __init__(
        self,
        *,
        model: str,
        client: Any | None = None,
        reasoning_effort: str | None = None,
        chair_reasoning_effort: str | None = None,
        max_output_tokens: int = 2500,
        chair_max_output_tokens: int = 6000,
        chair_retry_max_output_tokens: int = 8000,
        pricing_per_million: dict[str, float] | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        if min(max_output_tokens, chair_max_output_tokens, chair_retry_max_output_tokens) < 1:
            raise ValueError("output-token limits must be positive")
        self._model = model
        self._client = client or OpenAI()
        self._reasoning_effort = reasoning_effort
        self._chair_reasoning_effort = chair_reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._chair_max_output_tokens = chair_max_output_tokens
        self._chair_retry_max_output_tokens = chair_retry_max_output_tokens
        self._pricing = pricing_per_million or self._DEFAULT_PRICING.get(model)
        self.usage_records: list[dict[str, Any]] = []

    @classmethod
    def from_env(cls) -> OpenAIResponsesClient:
        model = environ.get("OPENAI_MODEL", "")
        if not model:
            raise RuntimeError("OPENAI_MODEL must be set")
        configured = {
            "input": environ.get("OPENAI_INPUT_COST_PER_MILLION"),
            "cached_input": environ.get("OPENAI_CACHED_INPUT_COST_PER_MILLION"),
            "output": environ.get("OPENAI_OUTPUT_COST_PER_MILLION"),
        }
        pricing = (
            {key: float(value) for key, value in configured.items() if value is not None}
            if all(value is not None for value in configured.values())
            else None
        )
        return cls(
            model=model,
            reasoning_effort=environ.get("OPENAI_REASONING_EFFORT") or None,
            chair_reasoning_effort=environ.get("OPENAI_CHAIR_REASONING_EFFORT") or None,
            max_output_tokens=int(environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2500")),
            chair_max_output_tokens=int(environ.get("OPENAI_CHAIR_MAX_OUTPUT_TOKENS", "6000")),
            chair_retry_max_output_tokens=int(
                environ.get("OPENAI_CHAIR_RETRY_MAX_OUTPUT_TOKENS", "8000")
            ),
            pricing_per_million=pricing,
        )

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT:
        is_chair = output_type.__name__ == "LiveChairDetermination"
        return self._generate(
            instructions=instructions,
            input_text=input_text,
            output_type=output_type,
            max_output_tokens=self._chair_max_output_tokens if is_chair else self._max_output_tokens,
            attempt="initial",
        )

    def repair(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT:
        """Retry one structured result with a larger Chair-only budget."""

        return self._generate(
            instructions=instructions,
            input_text=input_text,
            output_type=output_type,
            max_output_tokens=self._chair_retry_max_output_tokens,
            attempt="repair",
        )

    def _generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
        max_output_tokens: int,
        attempt: str,
    ) -> OutputT:
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": instructions,
            "input": input_text,
            "text_format": output_type,
            "store": False,
            "max_output_tokens": max_output_tokens,
        }
        effort = (
            self._chair_reasoning_effort
            if output_type.__name__ == "LiveChairDetermination" and self._chair_reasoning_effort
            else self._reasoning_effort
        )
        if effort:
            request["reasoning"] = {"effort": effort}
        try:
            response = self._client.responses.parse(**request)
        except (ValidationError, json.JSONDecodeError, openai.APIResponseValidationError) as exc:
            self._record_failed_attempt(output_type, attempt, max_output_tokens, "malformed")
            raise MalformedStructuredOutputError(
                f"{output_type.__name__} returned malformed structured output"
            ) from exc
        except openai.LengthFinishReasonError as exc:
            self._record_failed_attempt(output_type, attempt, max_output_tokens, "max_output_tokens")
            raise IncompleteResponseError(
                f"{output_type.__name__} was incomplete: max_output_tokens"
            ) from exc

        status = getattr(response, "status", None)
        details = getattr(response, "incomplete_details", None)
        reason = (
            details.get("reason")
            if isinstance(details, dict)
            else getattr(details, "reason", None)
            if details is not None
            else None
        )
        self._record_usage(response, output_type, attempt, max_output_tokens, status, reason)
        if status == "incomplete":
            raise IncompleteResponseError(
                f"{output_type.__name__} was incomplete: {reason or 'unknown'}"
            )
        if status not in (None, "completed"):
            raise IncompleteResponseError(f"{output_type.__name__} response status was {status}")
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise MalformedStructuredOutputError(
                f"{output_type.__name__} did not contain parsed output"
            )
        try:
            return cast(OutputT, output_type.model_validate(parsed))
        except ValidationError as exc:
            raise MalformedStructuredOutputError(
                f"{output_type.__name__} failed schema validation"
            ) from exc

    def _record_failed_attempt(
        self, output_type: type[BaseModel], attempt: str, limit: int, reason: str
    ) -> None:
        self.usage_records.append(
            {
                "stage": output_type.__name__,
                "attempt": attempt,
                "model": self._model,
                "status": "failed",
                "incomplete_reason": reason,
                "max_output_tokens": limit,
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "estimated_api_cost_usd": None,
            }
        )

    def _record_usage(
        self,
        response: Any,
        output_type: type[BaseModel],
        attempt: str,
        limit: int,
        status: str | None,
        reason: str | None,
    ) -> None:
        usage = getattr(response, "usage", None)
        input_tokens = _nested_int(usage, "input_tokens")
        cached_tokens = _nested_int(usage, "input_tokens_details", "cached_tokens")
        output_tokens = _nested_int(usage, "output_tokens")
        reasoning_tokens = _nested_int(usage, "output_tokens_details", "reasoning_tokens")
        cost = None
        if self._pricing is not None:
            uncached = max(0, input_tokens - cached_tokens)
            cost = round(
                (
                    uncached * self._pricing["input"]
                    + cached_tokens * self._pricing["cached_input"]
                    + output_tokens * self._pricing["output"]
                )
                / 1_000_000,
                8,
            )
        self.usage_records.append(
            {
                "stage": output_type.__name__,
                "attempt": attempt,
                "model": getattr(response, "model", None) or self._model,
                "status": status or "completed",
                "incomplete_reason": reason,
                "max_output_tokens": limit,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "estimated_api_cost_usd": cost,
            }
        )
