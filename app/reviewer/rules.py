from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

# Default path works both locally and in Docker (workdir=/app)
_DEFAULT_RULES_PATH = Path(__file__).parent.parent.parent / "rules" / "rules.yaml"


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    prompt: str


def load_rules(path: Path = _DEFAULT_RULES_PATH) -> list[Rule]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return [Rule(id=r["id"], name=r["name"], prompt=r["prompt"]) for r in data["rules"]]


def ruleset_version(path: Path = _DEFAULT_RULES_PATH) -> str:
    """SHA-256 of the rules file; changing any rule invalidates the reuse cache."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
