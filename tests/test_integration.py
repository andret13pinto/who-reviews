from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from who_reviews.config import load_config
from who_reviews.github_client import GitHubClient
from who_reviews.reviewer_selector import ReviewerSelector
from who_reviews.strategies import RandomStrategy

REPO = "org/test-repo"
PR_NUMBER = 99
AUTHOR = "alice"
BASE_URL = "https://api.github.com"


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    config_data = {
        "strategy": "random",
        "squads": [
            {
                "name": "payments",
                "members": ["alice", "bob", "charlie"],
                "paths": ["src/payments/**", "src/billing/**"],
            },
            {
                "name": "platform",
                "members": ["dave", "eve", "frank"],
                "paths": ["src/infra/**", "src/auth/**"],
            },
            {
                "name": "growth",
                "members": ["grace", "heidi"],
                "paths": ["src/growth/**"],
            },
        ],
    }
    path = tmp_path / "squads.yml"
    path.write_text(yaml.dump(config_data))
    return path


@pytest.fixture()
def event_file(tmp_path: Path) -> Path:
    event = {"pull_request": {"number": PR_NUMBER}}
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event))
    return path


def _mock_pr_endpoint(mock: respx.MockRouter, author: str = AUTHOR) -> respx.Route:
    return mock.get(f"/repos/{REPO}/pulls/{PR_NUMBER}").mock(
        return_value=httpx.Response(200, json={"user": {"login": author}})
    )


def _mock_files_endpoint(mock: respx.MockRouter, filenames: list[str]) -> respx.Route:
    page1 = [{"filename": f} for f in filenames]
    return mock.get(f"/repos/{REPO}/pulls/{PR_NUMBER}/files").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=[]),
        ]
    )


def _mock_collaborators_endpoint(
    mock: respx.MockRouter, logins: list[str] | None = None
) -> respx.Route:
    if logins is None:
        logins = ["alice", "bob", "charlie", "dave", "eve", "frank", "grace", "heidi"]
    page1 = [{"login": login} for login in logins]
    return mock.get(f"/repos/{REPO}/collaborators").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=[]),
        ]
    )


def _mock_assign_endpoint(mock: respx.MockRouter) -> respx.Route:
    return mock.post(f"/repos/{REPO}/pulls/{PR_NUMBER}/requested_reviewers").mock(
        return_value=httpx.Response(201, json={})
    )


def _run_full_flow(
    mock: respx.MockRouter,
    config_path: Path,
    changed_files: list[str],
    author: str = AUTHOR,
    collaborator_logins: list[str] | None = None,
) -> list[str]:
    _mock_pr_endpoint(mock, author)
    _mock_files_endpoint(mock, changed_files)
    _mock_collaborators_endpoint(mock, collaborator_logins)
    _mock_assign_endpoint(mock)

    config = load_config(config_path)
    client = GitHubClient(token="fake-token")
    strategy = RandomStrategy()
    selector = ReviewerSelector(config, strategy)

    files = client.get_changed_files(REPO, PR_NUMBER)
    pr_author = client.get_pr_author(REPO, PR_NUMBER)
    collaborators = client.get_collaborators(REPO)
    reviewers = selector.select_reviewers(
        files, pr_author, REPO, PR_NUMBER, collaborators
    )

    if reviewers:
        client.assign_reviewers(REPO, PR_NUMBER, reviewers)

    return reviewers


class TestSingleSquadFlow:
    @respx.mock(base_url=BASE_URL)
    def test_assigns_reviewers_from_squad_and_outsider(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        reviewers = _run_full_flow(
            respx_mock, config_file, changed_files=["src/payments/stripe.py"]
        )

        assert len(reviewers) == 2
        assert AUTHOR not in reviewers

    @respx.mock(base_url=BASE_URL)
    def test_squad_member_is_from_affected_squad(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        reviewers = _run_full_flow(
            respx_mock, config_file, changed_files=["src/payments/stripe.py"]
        )

        payments_members = {"bob", "charlie"}  # alice excluded as author
        outsiders = {"dave", "eve", "frank", "grace", "heidi"}

        assert reviewers[0] in payments_members
        assert reviewers[1] in outsiders


class TestMultiSquadFlow:
    @respx.mock(base_url=BASE_URL)
    def test_assigns_one_per_squad_plus_outsider(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        reviewers = _run_full_flow(
            respx_mock,
            config_file,
            changed_files=["src/payments/stripe.py", "src/infra/deploy.py"],
        )

        assert len(reviewers) == 3
        assert AUTHOR not in reviewers

        payments_members = {"bob", "charlie"}
        platform_members = {"dave", "eve", "frank"}
        growth_members = {"grace", "heidi"}

        assert reviewers[0] in payments_members
        assert reviewers[1] in platform_members
        assert reviewers[2] in growth_members


class TestNoOwnershipFlow:
    @respx.mock(base_url=BASE_URL)
    def test_assigns_two_random_reviewers(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        reviewers = _run_full_flow(
            respx_mock, config_file, changed_files=["README.md", "docs/guide.md"]
        )

        assert len(reviewers) == 2
        assert AUTHOR not in reviewers


class TestGitHubApiInteraction:
    @respx.mock(base_url=BASE_URL)
    def test_calls_assign_endpoint_with_reviewers(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        _mock_pr_endpoint(respx_mock)
        _mock_files_endpoint(respx_mock, ["src/payments/stripe.py"])
        _mock_collaborators_endpoint(respx_mock)
        assign_route = _mock_assign_endpoint(respx_mock)

        config = load_config(config_file)
        client = GitHubClient(token="fake-token")
        selector = ReviewerSelector(config, RandomStrategy())

        files = client.get_changed_files(REPO, PR_NUMBER)
        author = client.get_pr_author(REPO, PR_NUMBER)
        collaborators = client.get_collaborators(REPO)
        reviewers = selector.select_reviewers(
            files, author, REPO, PR_NUMBER, collaborators
        )
        client.assign_reviewers(REPO, PR_NUMBER, reviewers)

        assert assign_route.called
        body = json.loads(assign_route.calls.last.request.content)
        assert set(body["reviewers"]) == set(reviewers)

    @respx.mock(base_url=BASE_URL)
    def test_paginates_changed_files(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        page1 = [{"filename": f"src/payments/file{i}.py"} for i in range(100)]
        page2 = [{"filename": "src/infra/deploy.py"}]

        respx_mock.get(f"/repos/{REPO}/pulls/{PR_NUMBER}/files").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
                httpx.Response(200, json=[]),
            ]
        )

        client = GitHubClient(token="fake-token")
        files = client.get_changed_files(REPO, PR_NUMBER)

        assert len(files) == 101


class TestRetryIntegration:
    @respx.mock(base_url=BASE_URL, assert_all_called=False)
    def test_retries_on_502_then_succeeds(
        self, config_file: Path, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.get(f"/repos/{REPO}/pulls/{PR_NUMBER}/files").mock(
            side_effect=[
                httpx.Response(502),
                httpx.Response(200, json=[{"filename": "src/payments/stripe.py"}]),
                httpx.Response(200, json=[]),
            ]
        )

        client = GitHubClient(token="fake-token", max_retries=3, backoff_base=0.0)
        files = client.get_changed_files(REPO, PR_NUMBER)

        assert files == ["src/payments/stripe.py"]


class TestMainEntryPoint:
    @respx.mock(base_url=BASE_URL)
    def test_end_to_end_via_env_vars(
        self,
        config_file: Path,
        event_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        respx_mock: respx.MockRouter,
    ) -> None:
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
        monkeypatch.setenv("INPUT_GITHUB-TOKEN", "fake-token")
        monkeypatch.setenv("INPUT_CONFIG-PATH", str(config_file))

        _mock_pr_endpoint(respx_mock)
        _mock_files_endpoint(respx_mock, ["src/payments/stripe.py"])
        _mock_collaborators_endpoint(respx_mock)
        assign_route = _mock_assign_endpoint(respx_mock)

        from who_reviews.main import run

        run()

        assert assign_route.called
        body = json.loads(assign_route.calls.last.request.content)
        assert len(body["reviewers"]) == 2
        assert AUTHOR not in body["reviewers"]
