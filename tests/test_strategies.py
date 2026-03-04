from __future__ import annotations

import json
from pathlib import Path

import pytest

from pr_review_action.strategies import (
    LeastRecentStrategy,
    RandomStrategy,
    RoundRobinStrategy,
    SelectionContext,
)


@pytest.fixture()
def ctx() -> SelectionContext:
    return SelectionContext(repo="org/repo", pr_number=1, role="test")


@pytest.fixture()
def candidates() -> list[str]:
    return ["alice", "bob", "charlie"]


class TestRandomStrategy:
    def test_selects_from_candidates(
        self, candidates: list[str], ctx: SelectionContext
    ) -> None:
        strategy = RandomStrategy()
        result = strategy.select(candidates, ctx)
        assert result in candidates

    def test_single_candidate(self, ctx: SelectionContext) -> None:
        result = RandomStrategy().select(["alice"], ctx)
        assert result == "alice"


class TestRoundRobinStrategy:
    def test_distributes_evenly(self, tmp_path: Path, ctx: SelectionContext) -> None:
        state_path = tmp_path / "state.json"
        strategy = RoundRobinStrategy(state_path=state_path)
        candidates = ["alice", "bob"]

        picks = [strategy.select(candidates, ctx) for _ in range(4)]

        assert picks.count("alice") == 2
        assert picks.count("bob") == 2

    def test_picks_least_assigned(self, tmp_path: Path, ctx: SelectionContext) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"assignment_counts": {"alice": 5, "bob": 1}}))
        strategy = RoundRobinStrategy(state_path=state_path)

        result = strategy.select(["alice", "bob"], ctx)
        assert result == "bob"

    def test_persists_state(self, tmp_path: Path, ctx: SelectionContext) -> None:
        state_path = tmp_path / "state.json"
        strategy = RoundRobinStrategy(state_path=state_path)

        strategy.select(["alice", "bob"], ctx)

        data = json.loads(state_path.read_text())
        assert "assignment_counts" in data

    def test_state_survives_reinstantiation(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        candidates = ["alice", "bob"]

        first = RoundRobinStrategy(state_path=state_path)
        first.select(candidates, ctx)  # picks alice (count 0), bumps to 1

        second = RoundRobinStrategy(state_path=state_path)
        result = second.select(candidates, ctx)

        assert result == "bob"

    def test_new_candidate_joins_existing_state(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"assignment_counts": {"alice": 3, "bob": 2}}))
        strategy = RoundRobinStrategy(state_path=state_path)

        result = strategy.select(["alice", "bob", "charlie"], ctx)

        assert result == "charlie"

    def test_fair_distribution_over_many_rounds(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        candidates = ["alice", "bob", "charlie"]
        strategy = RoundRobinStrategy(state_path=state_path)

        picks = [strategy.select(candidates, ctx) for _ in range(6)]

        assert picks.count("alice") == 2
        assert picks.count("bob") == 2
        assert picks.count("charlie") == 2


class TestLeastRecentStrategy:
    def test_picks_never_assigned(self, tmp_path: Path, ctx: SelectionContext) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"last_assigned": {"alice": 1000.0}}))
        strategy = LeastRecentStrategy(state_path=state_path)

        result = strategy.select(["alice", "bob"], ctx)
        assert result == "bob"

    def test_picks_oldest_assignment(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"last_assigned": {"alice": 200.0, "bob": 100.0}})
        )
        strategy = LeastRecentStrategy(state_path=state_path)

        result = strategy.select(["alice", "bob"], ctx)
        assert result == "bob"

    def test_persists_timestamp(self, tmp_path: Path, ctx: SelectionContext) -> None:
        state_path = tmp_path / "state.json"
        strategy = LeastRecentStrategy(state_path=state_path)

        strategy.select(["alice"], ctx)

        data = json.loads(state_path.read_text())
        assert "last_assigned" in data
        assert data["last_assigned"]["alice"] > 0

    def test_state_survives_reinstantiation(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        candidates = ["alice", "bob"]

        first = LeastRecentStrategy(state_path=state_path)
        first_pick = first.select(candidates, ctx)

        second = LeastRecentStrategy(state_path=state_path)
        second_pick = second.select(candidates, ctx)

        assert first_pick != second_pick

    def test_new_candidate_joins_existing_state(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"last_assigned": {"alice": 1000.0, "bob": 2000.0}})
        )
        strategy = LeastRecentStrategy(state_path=state_path)

        result = strategy.select(["alice", "bob", "charlie"], ctx)

        assert result == "charlie"

    def test_selection_updates_timestamp(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"last_assigned": {"alice": 100.0, "bob": 200.0}})
        )
        strategy = LeastRecentStrategy(state_path=state_path)

        strategy.select(["alice", "bob"], ctx)  # picks alice (oldest)

        data = json.loads(state_path.read_text())
        assert data["last_assigned"]["alice"] > data["last_assigned"]["bob"]


class TestSharedStateFile:
    def test_strategies_coexist_without_corruption(
        self, tmp_path: Path, ctx: SelectionContext
    ) -> None:
        state_path = tmp_path / "state.json"
        candidates = ["alice", "bob"]

        rr = RoundRobinStrategy(state_path=state_path)
        lr = LeastRecentStrategy(state_path=state_path)

        rr.select(candidates, ctx)
        lr.select(candidates, ctx)

        data = json.loads(state_path.read_text())
        assert "assignment_counts" in data
        assert "last_assigned" in data
        assert set(data["assignment_counts"]) & set(candidates)
        assert set(data["last_assigned"]) & set(candidates)
