from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from who_reviews.config import ReviewConfig, load_config
from who_reviews.github_client import GitHubClient
from who_reviews.reviewer_selector import ReviewerSelector
from who_reviews.slack_client import SlackClient
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


def _resolve_teams(config: ReviewConfig, client: GitHubClient, org: str) -> None:
    for squad in config.squads:
        if squad.team:
            team_members = client.get_team_members(org, squad.team)
            merged = set(squad.members) | set(team_members)
            squad.members = sorted(merged)


def _resolve_outsiders(
    config: ReviewConfig, client: GitHubClient, repo: str, org: str
) -> list[str] | None:
    if config.outsider_source == "contributors":
        return client.get_contributors(repo)
    if config.outsider_source == "collaborators":
        return client.get_collaborators(repo)
    if config.outsider_source == "team" and config.outsider_team:
        return client.get_team_members(org, config.outsider_team)
    return None


def run() -> None:
    event_path = os.environ["GITHUB_EVENT_PATH"]
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["INPUT_GITHUB-TOKEN"]
    config_path = Path(os.environ.get("INPUT_CONFIG-PATH", ".github/squads.yml"))
    slack_webhook = os.environ.get("INPUT_SLACK-WEBHOOK", "").strip()

    org = repo.split("/")[0]

    with open(event_path) as f:
        event = json.load(f)

    pr = event["pull_request"]
    pr_number: int = pr["number"]
    pr_title: str = pr["title"]
    pr_url: str = pr["html_url"]
    pr_author_login: str = pr["user"]["login"]

    config = load_config(config_path)
    strategy = _build_strategy(config.strategy)
    client = GitHubClient(token)

    _resolve_teams(config, client, org)

    selector = ReviewerSelector(config, strategy)

    changed_files = client.get_changed_files(repo, pr_number)
    author = client.get_pr_author(repo, pr_number)
    outsiders = _resolve_outsiders(config, client, repo, org)

    reviewers = selector.select_reviewers(
        changed_files, author, repo, pr_number, outsiders
    )

    if reviewers:
        client.assign_reviewers(repo, pr_number, reviewers)
        print(f"Assigned reviewers: {', '.join(reviewers)}")

        if slack_webhook:
            mentions = []
            for reviewer in reviewers:
                handle = config.slack_handles.get(reviewer)
                if handle:
                    # Typical Slack user IDs start with U or W.
                    # Wrap in <@...> for mentions. Otherwise use @name.
                    if handle.startswith("U") or handle.startswith("W"):
                        mentions.append(f"<@{handle}>")
                    else:
                        mentions.append(f"@{handle}")
                else:
                    mentions.append(f"@{reviewer}")
            mentions_str = ", ".join(mentions)

            author_handle = config.slack_handles.get(pr_author_login)
            if author_handle:
                if author_handle.startswith("U") or author_handle.startswith("W"):
                    author_handle = f"<@{author_handle}>"
                else:
                    author_handle = f"@{author_handle}"
            else:
                author_handle = f"@{pr_author_login}"

            message = (
                f"<{pr_url}|{pr_title}>\n"
                f"Author: {author_handle}\n"
                f"Assigned to: {mentions_str}"
            )
            slack_client = SlackClient(webhook_url=slack_webhook)
            try:
                slack_client.send_message(message)
                print("Slack notification sent successfully.")
            except Exception as e:
                print(f"Failed to send Slack notification: {e}")
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
