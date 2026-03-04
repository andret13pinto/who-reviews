from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict


@dataclass(frozen=True)
class SelectionContext:
    repo: str
    pr_number: int
    role: str


class ReviewState(TypedDict, total=False):
    last_assigned: dict[str, float]
    assignment_counts: dict[str, int]


class SelectionStrategy(Protocol):
    def select(self, candidates: list[str], context: SelectionContext) -> str: ...
