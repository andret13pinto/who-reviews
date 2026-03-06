from __future__ import annotations

import httpx

from who_reviews.http_retry import RetryTransport


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
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            files.extend(item["filename"] for item in batch)
            page += 1
        return files

    def get_pr_author(self, repo: str, pr_number: int) -> str:
        response = self._client.get(f"/repos/{repo}/pulls/{pr_number}")
        response.raise_for_status()
        login: str = response.json()["user"]["login"]
        return login

    def get_contributors(self, repo: str) -> list[str]:
        return self._paginate_logins(f"/repos/{repo}/contributors")

    def get_collaborators(self, repo: str) -> list[str]:
        return self._paginate_logins(f"/repos/{repo}/collaborators")

    def _paginate_logins(self, url: str) -> list[str]:
        logins: list[str] = []
        page = 1
        while True:
            response = self._client.get(
                url,
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
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
        response.raise_for_status()
