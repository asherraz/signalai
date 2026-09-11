from types import SimpleNamespace

import pytest

from signalai.client import OpenAIResponsesClient
from signalai.schemas import ClaimSet


class FakeResponses:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.kwargs: dict[str, object] | None = None

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


def test_responses_client_uses_typed_parse_without_server_storage() -> None:
    parsed = ClaimSet.model_validate(
        {
            "claims": [
                {
                    "claim_id": "claim-1",
                    "program_id": "SGL-001",
                    "statement": "Fixture-supported claim",
                    "evidence_ids": ["evidence-1"],
                }
            ]
        }
    )
    responses = FakeResponses(parsed)
    sdk = SimpleNamespace(responses=responses)
    client = OpenAIResponsesClient(model="test-model", client=sdk)

    result = client.generate(
        instructions="research",
        input_text="fixture evidence",
        output_type=ClaimSet,
    )

    assert result is parsed
    assert responses.kwargs == {
        "model": "test-model",
        "instructions": "research",
        "input": "fixture evidence",
        "text_format": ClaimSet,
            "store": False,
            "max_output_tokens": 2500,
        }


def test_responses_client_rejects_missing_parsed_output() -> None:
    sdk = SimpleNamespace(responses=FakeResponses(None))
    client = OpenAIResponsesClient(model="test-model", client=sdk)

    with pytest.raises(RuntimeError, match="parsed output"):
        client.generate(instructions="role", input_text="input", output_type=ClaimSet)
