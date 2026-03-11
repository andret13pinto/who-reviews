from __future__ import annotations

import httpx
import pytest
import respx

from who_reviews.slack_client import SlackClient


class TestSlackClient:
    @respx.mock
    def test_send_message_success(self) -> None:
        webhook_url = "https://hooks.slack.com/webhook"
        respx.post(webhook_url).mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )

        client = SlackClient(webhook_url=webhook_url)
        client.send_message("Hello, world!")

        assert respx.calls.call_count == 1
        request = respx.calls.last.request
        assert request.method == "POST"
        assert request.url == webhook_url
        assert request.headers["Content-Type"] == "application/json"
        assert b'"text":"Hello,world!"' in request.content.replace(b" ", b"")

    @respx.mock
    def test_send_message_failure(self) -> None:
        webhook_url = "https://hooks.slack.com/webhook"
        respx.post(webhook_url).mock(
            return_value=httpx.Response(500, text="internal server error")
        )

        client = SlackClient(webhook_url=webhook_url, max_retries=1, backoff_base=0.1)

        with pytest.raises(httpx.HTTPStatusError):
            client.send_message("Hello, world!")
