import pytest

from app.models import RuleResult
from app.reviewer.engine import _parse_passed, review
from app.reviewer.rules import Rule

# --- fixtures ---

RULES = [
    Rule(id="rule_a", name="Meaningful names", prompt="Check variable names."),
    Rule(id="rule_b", name="Docstring matches", prompt="Check docstrings."),
]

SAMPLE_CODE = """
def add(x, y):
    \"\"\"Adds two numbers.\"\"\"
    return x + y
"""


class MockClient:
    """Injects a fixed response; records every prompt it receives."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


class PerRuleClient:
    """Returns different responses for successive calls."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    def generate(self, prompt: str) -> str:
        return next(self._responses)


# --- _parse_passed ---


def test_parse_passed_true():
    assert _parse_passed('{"passed": true}') is True


def test_parse_passed_false():
    assert _parse_passed('{"passed": false}') is False


def test_parse_passed_fallback_on_malformed_json():
    assert _parse_passed("not json at all") is False


def test_parse_passed_fallback_finds_true_literal():
    assert _parse_passed('some text "passed": true more text') is True


def test_parse_passed_fallback_returns_false_when_ambiguous():
    assert _parse_passed("{}") is False


# --- review: result shape ---


def test_review_returns_one_result_per_rule():
    client = MockClient('{"passed": true}')
    results = review(SAMPLE_CODE, RULES, client)
    assert len(results) == len(RULES)


def test_review_result_is_rule_result_type():
    client = MockClient('{"passed": true}')
    results = review(SAMPLE_CODE, RULES, client)
    assert isinstance(results[0], RuleResult)


def test_review_sets_rule_id():
    client = MockClient('{"passed": true}')
    results = review(SAMPLE_CODE, RULES, client)
    assert results[0].rule_id == "rule_a"


def test_review_sets_rule_name():
    client = MockClient('{"passed": true}')
    results = review(SAMPLE_CODE, RULES, client)
    assert results[0].name == "Meaningful names"


def test_review_passed_true_when_llm_returns_true():
    client = MockClient('{"passed": true}')
    results = review(SAMPLE_CODE, RULES, client)
    assert results[0].passed is True


def test_review_passed_false_when_llm_returns_false():
    client = MockClient('{"passed": false}')
    results = review(SAMPLE_CODE, RULES, client)
    assert results[0].passed is False


# --- review: one call per rule ---


def test_review_calls_llm_once_per_rule():
    client = MockClient('{"passed": true}')
    review(SAMPLE_CODE, RULES, client)
    assert len(client.prompts) == len(RULES)


def test_review_includes_code_in_prompt():
    client = MockClient('{"passed": true}')
    review(SAMPLE_CODE, RULES, client)
    assert SAMPLE_CODE in client.prompts[0]


def test_review_includes_rule_prompt_in_prompt():
    client = MockClient('{"passed": true}')
    review(SAMPLE_CODE, RULES, client)
    assert RULES[0].prompt.strip() in client.prompts[0]


# --- review: per-rule independence ---


def test_review_second_rule_uses_its_own_result():
    client = PerRuleClient(['{"passed": true}', '{"passed": false}'])
    results = review(SAMPLE_CODE, RULES, client)
    assert results[1].passed is False


# --- review: error resilience ---


def test_review_defaults_to_false_on_llm_exception():
    class ErrorClient:
        def generate(self, prompt: str) -> str:
            raise ConnectionError("Ollama unreachable")

    results = review(SAMPLE_CODE, [RULES[0]], ErrorClient())
    assert results[0].passed is False


def test_review_continues_after_one_rule_fails():
    class PartialErrorClient:
        def __init__(self):
            self._call = 0

        def generate(self, prompt: str) -> str:
            self._call += 1
            if self._call == 1:
                raise ConnectionError("first call fails")
            return '{"passed": true}'

    results = review(SAMPLE_CODE, RULES, PartialErrorClient())
    assert len(results) == 2
