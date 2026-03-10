from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from who_reviews.config import ReviewConfig, load_config


class TestReviewConfig:
    def test_valid_config(self, review_config: ReviewConfig) -> None:
        assert len(review_config.squads) == 3
        assert review_config.strategy == "random"

    @pytest.mark.parametrize("strategy", ["random", "round-robin", "least-recent"])
    def test_valid_strategies(self, strategy: str) -> None:
        config = ReviewConfig(
            strategy=strategy,  # type: ignore[arg-type]
            squads=[
                {"name": "a", "members": ["alice"], "paths": ["src/**"]},  # type: ignore[list-item]
            ],
        )
        assert config.strategy == strategy

    def test_rejects_invalid_strategy(self) -> None:
        with pytest.raises(ValueError):
            ReviewConfig(
                strategy="invalid",  # type: ignore[arg-type]
                squads=[
                    {"name": "a", "members": ["alice"], "paths": ["src/**"]},  # type: ignore[list-item]
                ],
            )

    def test_allows_shared_members_across_squads(self) -> None:
        config = ReviewConfig(
            strategy="random",
            squads=[
                {"name": "a", "members": ["alice", "bob"], "paths": ["src/a/**"]},  # type: ignore[list-item]
                {"name": "b", "members": ["alice"], "paths": ["src/b/**"]},  # type: ignore[list-item]
            ],
        )
        assert config.all_members == {"alice", "bob"}

    def test_rejects_no_members_and_no_team(self) -> None:
        with pytest.raises(ValueError, match="must have at least"):
            ReviewConfig(
                strategy="random",
                squads=[
                    {"name": "empty", "members": [], "paths": ["src/**"]},  # type: ignore[list-item]
                ],
            )

    def test_accepts_team_without_members(self) -> None:
        config = ReviewConfig(
            strategy="random",
            squads=[
                {"name": "a", "team": "my-team", "paths": ["src/**"]},  # type: ignore[list-item]
            ],
        )
        assert config.squads[0].team == "my-team"
        assert config.squads[0].members == []

    def test_accepts_team_with_members(self) -> None:
        config = ReviewConfig(
            strategy="random",
            squads=[
                {
                    "name": "a",
                    "team": "my-team",
                    "members": ["alice"],
                    "paths": ["src/**"],
                },  # type: ignore[list-item]
            ],
        )
        assert config.squads[0].team == "my-team"
        assert config.squads[0].members == ["alice"]

    def test_rejects_empty_paths(self) -> None:
        with pytest.raises(ValueError, match="has no paths"):
            ReviewConfig(
                strategy="random",
                squads=[
                    {"name": "no_paths", "members": ["alice"], "paths": []},  # type: ignore[list-item]
                ],
            )

    def test_all_members(self, review_config: ReviewConfig) -> None:
        expected = {"alice", "bob", "charlie", "dave", "eve", "frank", "grace", "heidi"}
        assert review_config.all_members == expected


class TestReviewerCountConfig:
    def test_defaults(self) -> None:
        config = ReviewConfig(
            squads=[{"name": "a", "members": ["alice"], "paths": ["src/**"]}],  # type: ignore[list-item]
        )
        assert config.squad_reviewers == 1
        assert config.outsider_reviewers == 1

    @pytest.mark.parametrize(
        ("squad_reviewers", "outsider_reviewers"),
        [(2, 3), (0, 0), (5, 0), (0, 5)],
    )
    def test_custom_values(self, squad_reviewers: int, outsider_reviewers: int) -> None:
        config = ReviewConfig(
            squads=[{"name": "a", "members": ["alice"], "paths": ["src/**"]}],  # type: ignore[list-item]
            squad_reviewers=squad_reviewers,
            outsider_reviewers=outsider_reviewers,
        )
        assert config.squad_reviewers == squad_reviewers
        assert config.outsider_reviewers == outsider_reviewers

    @pytest.mark.parametrize(
        ("squad_reviewers", "outsider_reviewers"),
        [(-1, 1), (1, -1), (-1, -1)],
    )
    def test_rejects_negative_values(
        self, squad_reviewers: int, outsider_reviewers: int
    ) -> None:
        with pytest.raises(ValueError):
            ReviewConfig(
                squads=[{"name": "a", "members": ["alice"], "paths": ["src/**"]}],  # type: ignore[list-item]
                squad_reviewers=squad_reviewers,
                outsider_reviewers=outsider_reviewers,
            )


class TestOutsiderTeamConfig:
    def test_outsider_source_team_requires_outsider_team(self) -> None:
        with pytest.raises(ValueError, match="outsider_team"):
            ReviewConfig(
                squads=[{"name": "a", "members": ["alice"], "paths": ["src/**"]}],  # type: ignore[list-item]
                outsider_source="team",
            )

    def test_outsider_source_team_with_outsider_team(self) -> None:
        config = ReviewConfig(
            squads=[{"name": "a", "members": ["alice"], "paths": ["src/**"]}],  # type: ignore[list-item]
            outsider_source="team",
            outsider_team="senior-devs",
        )
        assert config.outsider_team == "senior-devs"

    def test_has_team_refs_with_squad_team(self) -> None:
        config = ReviewConfig(
            squads=[{"name": "a", "team": "my-team", "paths": ["src/**"]}],  # type: ignore[list-item]
        )
        assert config.has_team_refs is True

    def test_has_team_refs_with_outsider_team(self) -> None:
        config = ReviewConfig(
            squads=[{"name": "a", "members": ["alice"], "paths": ["src/**"]}],  # type: ignore[list-item]
            outsider_source="team",
            outsider_team="senior-devs",
        )
        assert config.has_team_refs is True

    def test_has_team_refs_false_by_default(self, review_config: ReviewConfig) -> None:
        assert review_config.has_team_refs is False


class TestLoadConfig:
    def test_loads_from_yaml(self, tmp_path: Path) -> None:
        config_data = {
            "strategy": "round-robin",
            "squads": [
                {"name": "team", "members": ["alice", "bob"], "paths": ["src/**"]},
            ],
        }
        config_file = tmp_path / "squads.yml"
        config_file.write_text(yaml.dump(config_data))

        config = load_config(config_file)

        assert config.strategy == "round-robin"
        assert len(config.squads) == 1
        assert config.squads[0].name == "team"

    def test_loads_slack_handles(self, tmp_path: Path) -> None:
        config_data = {
            "strategy": "random",
            "slack_handles": {"alice": "U12345", "bob": "bob_slack"},
            "squads": [
                {"name": "team", "members": ["alice", "bob"], "paths": ["src/**"]},
            ],
        }
        config_file = tmp_path / "squads.yml"
        config_file.write_text(yaml.dump(config_data))

        config = load_config(config_file)

        assert config.slack_handles == {"alice": "U12345", "bob": "bob_slack"}
