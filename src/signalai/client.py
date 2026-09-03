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

    def __init__(self, *, model: str, client: Any | None = None) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self._model = model
        self._client = client or OpenAI()

    @classmethod
    def from_env(cls) -> OpenAIResponsesClient:
        model = environ.get("OPENAI_MODEL", "")
        if not model:
            raise RuntimeError("OPENAI_MODEL must be set")
        return cls(model=model)

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT:
        response = self._client.responses.parse(
            model=self._model,
            instructions=instructions,
            input=input_text,
            text_format=output_type,
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("OpenAI response did not contain a parsed output")
        return cast(OutputT, output_type.model_validate(parsed))
