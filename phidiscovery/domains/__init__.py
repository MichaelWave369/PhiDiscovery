"""Explicitly registered science-domain rule hooks; no runtime arbitrary imports."""
from typing import Callable

from .cannabinoids import ambiguity_flags

Rule = Callable[[dict, list[dict], list[dict]], list[str]]
RULES: dict[str, Rule] = {"cannabinoids": ambiguity_flags, "cannabinoid": ambiguity_flags}


def get_rule(domain: str) -> Rule | None:
    return RULES.get(domain.lower())
