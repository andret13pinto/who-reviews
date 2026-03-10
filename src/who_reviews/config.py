from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class SquadConfig(BaseModel):
    name: str
    members: list[str] = Field(default_factory=list)
    team: str | None = None
    paths: list[str]

    @model_validator(mode="after")
    def _validate_member_source(self) -> SquadConfig:
        if not self.members and not self.team:
            raise ValueError(
                f"Squad '{self.name}' must have at least 'members' or 'team'"
            )
        return self


class ReviewConfig(BaseModel):
    strategy: Literal["random", "round-robin", "least-recent"] = "random"
    squads: list[SquadConfig]
    squad_reviewers: int = Field(default=1, ge=0)
    outsider_reviewers: int = Field(default=1, ge=0)
    exclude: list[str] = Field(default_factory=list)
    outsider_source: Literal["contributors", "collaborators", "team"] | None = None
    outsider_team: str | None = None
    slack_handles: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_config(self) -> ReviewConfig:
        self._check_no_empty_paths()
        self._check_outsider_team()
        return self

    def _check_no_empty_paths(self) -> None:
        for squad in self.squads:
            if not squad.paths:
                raise ValueError(f"Squad '{squad.name}' has no paths")

    def _check_outsider_team(self) -> None:
        if self.outsider_source == "team" and not self.outsider_team:
            raise ValueError(
                "'outsider_team' is required when outsider_source is 'team'"
            )

    @property
    def all_members(self) -> set[str]:
        members: set[str] = set()
        for squad in self.squads:
            members.update(squad.members)
        return members

    @property
    def has_team_refs(self) -> bool:
        if self.outsider_source == "team":
            return True
        return any(squad.team for squad in self.squads)


def load_config(path: Path) -> ReviewConfig:
    raw = yaml.safe_load(path.read_text())
    return ReviewConfig.model_validate(raw)
