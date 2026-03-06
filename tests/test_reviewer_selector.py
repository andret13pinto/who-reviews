from __future__ import annotations

import pytest

from who_reviews.config import ReviewConfig
from who_reviews.reviewer_selector import ReviewerSelector
from who_reviews.strategies.base import SelectionStrategy

REPO = "org/repo"
PR = 42


class TestNoOwnership:
    """When no squad owns the changed files → 2 random reviewers."""

    def test_picks_two_reviewers(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["README.md"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        assert len(result) == 2

    def test_excludes_author(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["README.md"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        assert "alice" not in result

    def test_no_duplicates(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["README.md"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        assert len(result) == len(set(result))


class TestSingleSquad:
    """Single squad touched → 1 from squad + 1 outsider."""

    def test_one_from_squad_one_outsider(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        # 1 from payments squad (bob or charlie, since alice is author)
        # + 1 outsider (not in payments)
        assert len(result) == 2
        payments_members = {"bob", "charlie"}
        outsiders = review_config.all_members - {"alice", "bob", "charlie"}

        assert result[0] in payments_members
        assert result[1] in outsiders

    def test_excludes_author_from_squad(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="bob",
            repo=REPO,
            pr_number=PR,
        )

        assert "bob" not in result


class TestMultipleSquads:
    """Multiple squads touched → 1 from each + 1 outsider."""

    def test_one_per_squad_plus_outsider(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py", "src/infra/deploy.py"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        # 1 from payments + 1 from platform + 1 outsider (growth)
        assert len(result) == 3
        assert "alice" not in result

    def test_all_squads_touched(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=[
                "src/payments/stripe.py",
                "src/infra/deploy.py",
                "src/growth/ab.py",
            ],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        # 1 from each squad (3), no outsider possible (all squads affected)
        # but outsider pool is empty since all members belong to affected squads
        assert len(result) == 3
        assert "alice" not in result


class TestOverlappingSquads:
    """When a member belongs to multiple affected squads, they are only picked once."""

    def test_shared_member_not_picked_twice(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            strategy="random",
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "platform",
                    "members": ["alice", "charlie"],
                    "paths": ["src/infra/**"],
                },  # type: ignore[list-item]
                {
                    "name": "growth",
                    "members": ["dave", "eve"],
                    "paths": ["src/growth/**"],
                },  # type: ignore[list-item]
            ],
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py", "src/infra/deploy.py"],
            author="frank",
            repo=REPO,
            pr_number=PR,
        )

        assert len(result) == len(set(result))
        assert len(result) == 3  # 1 per squad + outsider

    def test_fully_overlapping_squads_still_picks_distinct(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            strategy="random",
            squads=[
                {"name": "a", "members": ["alice", "bob"], "paths": ["src/a/**"]},  # type: ignore[list-item]
                {"name": "b", "members": ["alice", "bob"], "paths": ["src/b/**"]},  # type: ignore[list-item]
                {"name": "other", "members": ["charlie"], "paths": ["lib/**"]},  # type: ignore[list-item]
            ],
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/a/foo.py", "src/b/bar.py"],
            author="charlie",
            repo=REPO,
            pr_number=PR,
        )

        # alice picked for squad a, bob for squad b, no outsider (charlie is author)
        assert result == ["alice", "bob"]
        assert len(result) == len(set(result))


class TestConfigurableReviewerCounts:
    """Verify squad_reviewers and outsider_reviewers config fields."""

    def test_two_squad_one_outsider(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob", "charlie"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "other",
                    "members": ["dave", "eve"],
                    "paths": ["lib/**"],
                },  # type: ignore[list-item]
            ],
            squad_reviewers=2,
            outsider_reviewers=1,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="frank",
            repo=REPO,
            pr_number=PR,
        )

        payments = {"alice", "bob", "charlie"}
        outsiders = config.all_members - payments - {"frank"}
        assert len(result) == 3
        assert set(result[:2]).issubset(payments)
        assert result[2] in outsiders

    def test_one_squad_two_outsiders(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "other",
                    "members": ["charlie", "dave", "eve"],
                    "paths": ["lib/**"],
                },  # type: ignore[list-item]
            ],
            squad_reviewers=1,
            outsider_reviewers=2,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="frank",
            repo=REPO,
            pr_number=PR,
        )

        payments = {"alice", "bob"}
        outsiders = config.all_members - payments - {"frank"}
        assert len(result) == 3
        assert result[0] in payments
        assert set(result[1:]).issubset(outsiders)

    def test_squad_only_no_outsider(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob", "charlie"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "other",
                    "members": ["dave"],
                    "paths": ["lib/**"],
                },  # type: ignore[list-item]
            ],
            squad_reviewers=1,
            outsider_reviewers=0,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="eve",
            repo=REPO,
            pr_number=PR,
        )

        payments = {"alice", "bob", "charlie"}
        assert len(result) == 1
        assert result[0] in payments

    def test_outsiders_only_no_squad(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "other",
                    "members": ["charlie", "dave", "eve"],
                    "paths": ["lib/**"],
                },  # type: ignore[list-item]
            ],
            squad_reviewers=0,
            outsider_reviewers=2,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="frank",
            repo=REPO,
            pr_number=PR,
        )

        payments = {"alice", "bob"}
        outsiders = config.all_members - payments - {"frank"}
        assert len(result) == 2
        assert set(result).issubset(outsiders)

    def test_no_ownership_custom_counts(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "a",
                    "members": ["alice", "bob", "charlie", "dave"],
                    "paths": ["src/**"],
                },  # type: ignore[list-item]
            ],
            squad_reviewers=2,
            outsider_reviewers=1,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["README.md"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        assert len(result) == 3
        assert "alice" not in result

    def test_not_enough_candidates_picks_available(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "other",
                    "members": ["charlie"],
                    "paths": ["lib/**"],
                },  # type: ignore[list-item]
            ],
            squad_reviewers=5,
            outsider_reviewers=5,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="dave",
            repo=REPO,
            pr_number=PR,
        )

        # Only 2 in payments squad, 1 outsider available
        assert len(result) <= 3
        assert len(result) == len(set(result))
        assert "dave" not in result


class TestCollaboratorsAsOutsiders:
    """Non-squad collaborators are eligible for the outsider pool."""

    def test_collaborator_picked_as_outsider(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
            ],
            outsider_reviewers=1,
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="alice",
            repo=REPO,
            pr_number=PR,
            collaborators=["charlie", "dave"],
        )

        # bob from squad, then charlie or dave as outsider
        assert len(result) == 2
        assert result[0] == "bob"
        assert result[1] in {"charlie", "dave"}

    def test_collaborator_in_no_ownership_fallback(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
            ],
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["README.md"],
            author="alice",
            repo=REPO,
            pr_number=PR,
            collaborators=["bob", "charlie"],
        )

        assert "alice" not in result
        assert len(result) == 2
        assert set(result).issubset({"bob", "charlie"})

    def test_excluded_collaborator_not_picked(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
            ],
            outsider_reviewers=1,
            exclude=["badbot"],
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="alice",
            repo=REPO,
            pr_number=PR,
            collaborators=["badbot", "charlie"],
        )

        assert "badbot" not in result
        assert result[1] == "charlie"

    def test_excluded_squad_member_not_picked(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            squads=[
                {
                    "name": "payments",
                    "members": ["alice", "bob", "charlie"],
                    "paths": ["src/payments/**"],
                },  # type: ignore[list-item]
                {
                    "name": "other",
                    "members": ["dave"],
                    "paths": ["lib/**"],
                },  # type: ignore[list-item]
            ],
            exclude=["bob"],
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["README.md"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        assert "bob" not in result

    def test_no_collaborators_falls_back_to_squad_members(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        # Behaves same as before — outsider comes from other squads
        assert len(result) == 2
        assert all(r in review_config.all_members for r in result)


class TestEdgeCases:
    def test_author_is_sole_squad_member_compensates_with_outsiders(
        self,
        deterministic_strategy: SelectionStrategy,
    ) -> None:
        config = ReviewConfig(
            strategy="random",
            squads=[
                {"name": "solo", "members": ["alice"], "paths": ["src/**"]},  # type: ignore[list-item]
                {"name": "other", "members": ["bob", "charlie"], "paths": ["lib/**"]},  # type: ignore[list-item]
            ],
        )
        selector = ReviewerSelector(config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/foo.py"],
            author="alice",
            repo=REPO,
            pr_number=PR,
        )

        # squad pick fails (alice is author and sole member), deficit of 1
        # compensated: 1 (outsider_reviewers) + 1 (deficit) = 2 outsiders
        assert "alice" not in result
        assert len(result) == 2

    @pytest.mark.parametrize(
        "author",
        ["alice", "bob", "charlie", "dave", "eve", "frank", "grace", "heidi"],
    )
    def test_author_always_excluded(
        self,
        review_config: ReviewConfig,
        deterministic_strategy: SelectionStrategy,
        author: str,
    ) -> None:
        selector = ReviewerSelector(review_config, deterministic_strategy)

        result = selector.select_reviewers(
            changed_files=["src/payments/stripe.py"],
            author=author,
            repo=REPO,
            pr_number=PR,
        )

        assert author not in result
