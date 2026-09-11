"""Typed OpenAI Responses API boundary."""

from __future__ import annotations

from os import environ
from typing import Any, Protocol, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel


OutputT = TypeVar("OutputT", bound=BaseModel)


class ModelClient(Protocol):
    """Minimal interface required by the Milestone 1 orchestrator."""

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT: ...


class OpenAIResponsesClient:
    """Generate Pydantic-validated outputs with the OpenAI Responses API."""

    def __init__(
        self,
        *,
        model: str,
        client: Any | None = None,
        reasoning_effort: str | None = None,
        chair_reasoning_effort: str | None = None,
        max_output_tokens: int = 2500,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self._model = model
        self._client = client or OpenAI()
        self._reasoning_effort = reasoning_effort
        self._chair_reasoning_effort = chair_reasoning_effort
        self._max_output_tokens = max_output_tokens
        self.usage_records: list[dict[str, Any]] = []

    @classmethod
    def from_env(cls) -> OpenAIResponsesClient:
        model = environ.get("OPENAI_MODEL", "")
        if not model:
            raise RuntimeError("OPENAI_MODEL must be set")
        return cls(
            model=model,
            reasoning_effort=environ.get("OPENAI_REASONING_EFFORT") or None,
            chair_reasoning_effort=environ.get("OPENAI_CHAIR_REASONING_EFFORT") or None,
            max_output_tokens=int(environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2500")),
        )

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT:
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": instructions,
            "input": input_text,
            "text_format": output_type,
            "store": False,
            "max_output_tokens": self._max_output_tokens,
        }
        effort = (
            self._chair_reasoning_effort
            if output_type.__name__ == "LiveChairDetermination" and self._chair_reasoning_effort
            else self._reasoning_effort
        )
        if effort:
            request["reasoning"] = {"effort": effort}
        response = self._client.responses.parse(
            **request,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            payload = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else {}
            self.usage_records.append({"model": self._model, "output_type": output_type.__name__, **payload})
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("OpenAI response did not contain a parsed output")
        return cast(OutputT, output_type.model_validate(parsed))
