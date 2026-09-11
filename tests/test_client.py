from types import SimpleNamespace

import pytest

from signalai.client import (
    IncompleteResponseError,
    MalformedStructuredOutputError,
    OpenAIResponsesClient,
)
from signalai.schemas import ClaimSet, LiveChairRecommendation


class FakeResponses:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.kwargs: dict[str, object] | None = None

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


class SequenceResponses:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


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

    with pytest.raises(MalformedStructuredOutputError, match="parsed output"):
        client.generate(instructions="role", input_text="input", output_type=ClaimSet)


def test_client_detects_incomplete_response_and_accounts_for_usage() -> None:
    usage = SimpleNamespace(
        input_tokens=1000,
        input_tokens_details=SimpleNamespace(cached_tokens=200),
        output_tokens=500,
        output_tokens_details=SimpleNamespace(reasoning_tokens=300),
    )
    response = SimpleNamespace(
        output_parsed=None,
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        usage=usage,
        model="gpt-5-mini",
    )
    client = OpenAIResponsesClient(
        model="gpt-5-mini", client=SimpleNamespace(responses=SequenceResponses([response]))
    )

    with pytest.raises(IncompleteResponseError, match="max_output_tokens"):
        client.generate(instructions="role", input_text="input", output_type=ClaimSet)

    record = client.usage_records[0]
    assert record == {
        "stage": "ClaimSet",
        "attempt": "initial",
        "model": "gpt-5-mini",
        "status": "incomplete",
        "incomplete_reason": "max_output_tokens",
        "max_output_tokens": 2500,
        "input_tokens": 1000,
        "cached_input_tokens": 200,
        "output_tokens": 500,
        "reasoning_tokens": 300,
        "estimated_api_cost_usd": 0.001205,
    }


def test_client_wraps_truncated_json_and_uses_chair_retry_budget() -> None:
    with pytest.raises(Exception) as captured:
        LiveChairRecommendation.model_validate_json('{"matter_id":"matter-1","risk_ids":[')
    truncated = captured.value
    parsed = SimpleNamespace(
        output_parsed={
            "matter_id": "matter-1",
            "findings": ["No supported change."],
            "evidence_assessment": "Evidence is unchanged.",
            "supporting_evidence_ids": [],
            "objections": ["Evidence remains limited."],
            "recommendation": "Retain the current position.",
            "proposed_changes": {},
        },
        status="completed",
        incomplete_details=None,
        usage=None,
        model="gpt-5-mini",
    )
    responses = SequenceResponses([truncated, parsed])
    client = OpenAIResponsesClient(
        model="gpt-5-mini", client=SimpleNamespace(responses=responses)
    )

    with pytest.raises(MalformedStructuredOutputError):
        client.generate(
            instructions="chair", input_text="bounded", output_type=LiveChairRecommendation
        )
    result = client.repair(
        instructions="repair", input_text="bounded", output_type=LiveChairRecommendation
    )

    assert result.recommendation == "Retain the current position."
    assert responses.calls[0]["max_output_tokens"] == 6000
    assert responses.calls[1]["max_output_tokens"] == 8000
