from __future__ import annotations

import httpx

from who_reviews.http_retry import RetryTransport


class GitHubAPIError(Exception):
    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        self.detail = _extract_error_detail(response)
        request = response.request
        super().__init__(
            f"GitHub API {request.method} {request.url.path} failed "
            f"with {self.status_code}: {self.detail}"
        )


class GitHubClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        *,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        transport = RetryTransport(
            max_retries=max_retries,
            backoff_base=backoff_base,
        )
        self._client = httpx.Client(
            base_url=base_url,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def get_changed_files(self, repo: str, pr_number: int) -> list[str]:
        files: list[str] = []
        page = 1
        while True:
            response = self._client.get(
                f"/repos/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            _raise_for_status(response)
            batch = response.json()
            if not batch:
                break
            files.extend(item["filename"] for item in batch)
            page += 1
        return files

    def get_pr_author(self, repo: str, pr_number: int) -> str:
        response = self._client.get(f"/repos/{repo}/pulls/{pr_number}")
        _raise_for_status(response)
        login: str = response.json()["user"]["login"]
        return login

    def get_contributors(self, repo: str) -> list[str]:
        return self._paginate_logins(f"/repos/{repo}/contributors")

    def get_collaborators(self, repo: str) -> list[str]:
        return self._paginate_logins(f"/repos/{repo}/collaborators")

    def get_team_members(self, org: str, team_slug: str) -> list[str]:
        return self._paginate_logins(f"/orgs/{org}/teams/{team_slug}/members")

    def _paginate_logins(self, url: str) -> list[str]:
        logins: list[str] = []
        page = 1
        while True:
            response = self._client.get(
                url,
                params={"per_page": 100, "page": page},
            )
            _raise_for_status(response)
            batch = response.json()
            if not batch:
                break
            logins.extend(item["login"] for item in batch)
            page += 1
        return logins

    def assign_reviewers(self, repo: str, pr_number: int, reviewers: list[str]) -> None:
        response = self._client.post(
            f"/repos/{repo}/pulls/{pr_number}/requested_reviewers",
            json={"reviewers": reviewers},
        )
        _raise_for_status(response)


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_error:
        raise GitHubAPIError(response)


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    if not isinstance(body, dict):
        return str(body)
    parts = [str(body.get("message", response.reason_phrase))]
    parts.extend(str(error) for error in body.get("errors", []))
    return "; ".join(parts)
