from __future__ import annotations

import httpx

from who_reviews.http_retry import RetryTransport


class SlackClient:
    def __init__(
        self,
        webhook_url: str,
        *,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        self.webhook_url = webhook_url
        transport = RetryTransport(
            max_retries=max_retries,
            backoff_base=backoff_base,
        )
        self._client = httpx.Client(
            transport=transport,
            headers={"Content-Type": "application/json"},
        )

    def send_message(self, text: str) -> None:
        response = self._client.post(self.webhook_url, json={"text": text})
        response.raise_for_status()
