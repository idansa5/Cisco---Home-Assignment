from __future__ import annotations

import json
import logging
from typing import Protocol

from app.models import RuleResult
from app.reviewer.rules import Rule

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """{rule_prompt}

Code to review:
```python
{code}
```"""


class LLMClient(Protocol):
    def generate(self, prompt: str) -> str: ...


def review(code: str, rules: list[Rule], client: LLMClient) -> list[RuleResult]:
    """Run each rule against the code via one LLM call; return a result per rule."""
    results = []
    for rule in rules:
        prompt = _PROMPT_TEMPLATE.format(rule_prompt=rule.prompt.strip(), code=code)
        try:
            raw = client.generate(prompt)
            passed = _parse_passed(raw)
        except Exception as exc:
            logger.warning("Rule %s failed with error: %s — defaulting to False", rule.id, exc)
            passed = False
        results.append(RuleResult(rule_id=rule.id, name=rule.name, passed=passed))
    return results


def _parse_passed(raw: str) -> bool:
    """Extract the boolean 'passed' field from a JSON response string."""
    try:
        return bool(json.loads(raw)["passed"])
    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: scan for true/false literals if the model wrapped the JSON
        lower = raw.lower()
        if '"passed": true' in lower or "'passed': true" in lower:
            return True
        return False
