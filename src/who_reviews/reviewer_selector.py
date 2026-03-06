from __future__ import annotations

from who_reviews.config import ReviewConfig, SquadConfig
from who_reviews.ownership import resolve_ownership
from who_reviews.strategies.base import SelectionContext, SelectionStrategy


class ReviewerSelector:
    def __init__(self, config: ReviewConfig, strategy: SelectionStrategy) -> None:
        self._config = config
        self._strategy = strategy

    def select_reviewers(
        self,
        changed_files: list[str],
        author: str,
        repo: str,
        pr_number: int,
        collaborators: list[str] | None = None,
    ) -> list[str]:
        affected_squads = resolve_ownership(changed_files, self._config)
        pool = self._build_pool(collaborators)

        if not affected_squads:
            return self._select_no_ownership(author, repo, pr_number, pool)

        return self._select_with_ownership(
            affected_squads, author, repo, pr_number, pool
        )

    def _build_pool(self, collaborators: list[str] | None) -> set[str]:
        pool = self._config.all_members.copy()
        if collaborators:
            pool.update(collaborators)
        pool -= set(self._config.exclude)
        return pool

    def _select_no_ownership(
        self, author: str, repo: str, pr_number: int, pool: set[str]
    ) -> list[str]:
        candidates = sorted(pool - {author})
        total = self._config.squad_reviewers + self._config.outsider_reviewers
        if not candidates or total == 0:
            return []

        reviewers: list[str] = []
        ctx = SelectionContext(repo=repo, pr_number=pr_number, role="fallback")
        for _ in range(min(total, len(candidates))):
            remaining = [c for c in candidates if c not in reviewers]
            if not remaining:
                break
            selected = self._strategy.select(remaining, ctx)
            reviewers.append(selected)

        return reviewers

    def _select_with_ownership(
        self,
        affected_squads: list[SquadConfig],
        author: str,
        repo: str,
        pr_number: int,
        pool: set[str],
    ) -> list[str]:
        reviewers: list[str] = []
        expected_squad_picks = 0

        for squad in affected_squads:
            ctx = SelectionContext(
                repo=repo, pr_number=pr_number, role=f"squad-{squad.name}"
            )
            for _ in range(self._config.squad_reviewers):
                expected_squad_picks += 1
                candidates = sorted(set(squad.members) - {author} - set(reviewers))
                if not candidates:
                    break
                selected = self._strategy.select(candidates, ctx)
                reviewers.append(selected)

        squad_deficit = expected_squad_picks - len(reviewers)
        outsiders = self._pick_outsiders(
            affected_squads, author, reviewers, repo, pr_number, pool, squad_deficit
        )
        reviewers.extend(outsiders)

        return reviewers

    def _pick_outsiders(
        self,
        affected_squads: list[SquadConfig],
        author: str,
        already_selected: list[str],
        repo: str,
        pr_number: int,
        pool: set[str],
        squad_deficit: int = 0,
    ) -> list[str]:
        affected_members: set[str] = set()
        for squad in affected_squads:
            affected_members.update(squad.members)

        outsider_candidates = sorted(
            pool - affected_members - {author} - set(already_selected)
        )
        if not outsider_candidates:
            return []

        ctx = SelectionContext(repo=repo, pr_number=pr_number, role="outsider")
        result: list[str] = []
        outsider_count = self._config.outsider_reviewers + squad_deficit
        for _ in range(outsider_count):
            remaining = [c for c in outsider_candidates if c not in result]
            if not remaining:
                break
            selected = self._strategy.select(remaining, ctx)
            result.append(selected)

        return result
