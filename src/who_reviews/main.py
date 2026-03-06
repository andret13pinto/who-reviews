from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from who_reviews.config import load_config
from who_reviews.github_client import GitHubClient
from who_reviews.reviewer_selector import ReviewerSelector
from who_reviews.strategies import (
    LeastRecentStrategy,
    RandomStrategy,
    RoundRobinStrategy,
    SelectionStrategy,
)


def _build_strategy(name: str) -> SelectionStrategy:
    strategies: dict[str, SelectionStrategy] = {
        "random": RandomStrategy(),
        "round-robin": RoundRobinStrategy(),
        "least-recent": LeastRecentStrategy(),
    }
    return strategies[name]


def run() -> None:
    event_path = os.environ["GITHUB_EVENT_PATH"]
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["INPUT_GITHUB-TOKEN"]
    config_path = Path(os.environ.get("INPUT_CONFIG-PATH", ".github/squads.yml"))

    with open(event_path) as f:
        event = json.load(f)

    pr_number: int = event["pull_request"]["number"]

    config = load_config(config_path)
    strategy = _build_strategy(config.strategy)
    client = GitHubClient(token)
    selector = ReviewerSelector(config, strategy)

    changed_files = client.get_changed_files(repo, pr_number)
    author = client.get_pr_author(repo, pr_number)
    collaborators = client.get_collaborators(repo)

    reviewers = selector.select_reviewers(
        changed_files, author, repo, pr_number, collaborators
    )

    if reviewers:
        client.assign_reviewers(repo, pr_number, reviewers)
        print(f"Assigned reviewers: {', '.join(reviewers)}")
    else:
        print("No eligible reviewers found")


def main() -> None:
    try:
        run()
    except Exception as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
