from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class SquadConfig(BaseModel):
    name: str
    members: list[str]
    paths: list[str]


class ReviewConfig(BaseModel):
    strategy: Literal["random", "round-robin", "least-recent"] = "random"
    squads: list[SquadConfig]
    squad_reviewers: int = Field(default=1, ge=0)
    outsider_reviewers: int = Field(default=1, ge=0)
    exclude: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_squads(self) -> ReviewConfig:
        self._check_no_empty_squads()
        return self

    def _check_no_empty_squads(self) -> None:
        for squad in self.squads:
            if not squad.members:
                raise ValueError(f"Squad '{squad.name}' has no members")
            if not squad.paths:
                raise ValueError(f"Squad '{squad.name}' has no paths")

    @property
    def all_members(self) -> set[str]:
        members: set[str] = set()
        for squad in self.squads:
            members.update(squad.members)
        return members


def load_config(path: Path) -> ReviewConfig:
    raw = yaml.safe_load(path.read_text())
    return ReviewConfig.model_validate(raw)
