from __future__ import annotations

import pytest

from empire_youtube.client import YouTubeClient
from empire_youtube.config import YouTubeAPIConfig
from empire_youtube.exceptions import YouTubeAPIError, YouTubeResponseError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"items": []}
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)


def test_search_video_request_construction():
    session = FakeSession([FakeResponse(payload={"items": []})])
    client = YouTubeClient(
        YouTubeAPIConfig(api_key="test-key", base_url="https://example.test"),
        session=session,
    )

    client.search_videos(
        "younger dryas",
        max_results=7,
        published_after="2026-05-22T00:00:00Z",
        relevance_language="en",
    )

    call = session.calls[0]
    assert call["url"] == "https://example.test/search"
    assert call["params"]["key"] == "test-key"
    assert call["params"]["part"] == "snippet"
    assert call["params"]["q"] == "younger dryas"
    assert call["params"]["type"] == "video"
    assert call["params"]["order"] == "date"
    assert call["params"]["maxResults"] == 7
    assert call["params"]["publishedAfter"] == "2026-05-22T00:00:00Z"
    assert call["params"]["relevanceLanguage"] == "en"


def test_get_videos_request_construction():
    session = FakeSession([FakeResponse(payload={"items": []})])
    client = YouTubeClient(
        YouTubeAPIConfig(api_key="test-key", base_url="https://example.test"),
        session=session,
    )

    client.get_videos(["a", "b"], parts=["snippet", "statistics"])

    call = session.calls[0]
    assert call["url"] == "https://example.test/videos"
    assert call["params"]["id"] == "a,b"
    assert call["params"]["part"] == "snippet,statistics"


def test_get_channel_uploads_playlist():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "items": [
                        {
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UU123"}
                            }
                        }
                    ]
                }
            )
        ]
    )
    client = YouTubeClient(YouTubeAPIConfig(api_key="test-key"), session=session)

    assert client.get_channel_uploads_playlist("UC123") == "UU123"


def test_http_error_raises_api_error():
    session = FakeSession([FakeResponse(status_code=403, payload={}, text="quota")])
    client = YouTubeClient(YouTubeAPIConfig(api_key="test-key"), session=session)

    with pytest.raises(YouTubeAPIError, match="HTTP 403"):
        client.search_channel("All-In Podcast")


def test_invalid_json_raises_response_error():
    session = FakeSession([FakeResponse(payload=ValueError("bad json"))])
    client = YouTubeClient(YouTubeAPIConfig(api_key="test-key"), session=session)

    with pytest.raises(YouTubeResponseError, match="invalid JSON"):
        client.search_channel("All-In Podcast")


def test_search_requests_are_throttled(monkeypatch):
    times = iter([100.0, 100.0, 102.0, 109.0])
    sleeps = []
    monkeypatch.setattr("empire_youtube.client.time.monotonic", lambda: next(times))
    monkeypatch.setattr(
        "empire_youtube.client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )
    session = FakeSession(
        [
            FakeResponse(payload={"items": []}),
            FakeResponse(payload={"items": []}),
        ]
    )
    client = YouTubeClient(
        YouTubeAPIConfig(api_key="test-key", base_url="https://example.test"),
        session=session,
        search_throttle_seconds=7.0,
    )

    client.search_channel("first")
    client.search_channel("second")

    assert sleeps == [5.0]


def test_video_hydration_is_not_search_throttled(monkeypatch):
    monkeypatch.setattr(
        "empire_youtube.client.time.sleep",
        lambda seconds: pytest.fail("video hydration should not throttle"),
    )
    session = FakeSession([FakeResponse(payload={"items": []})])
    client = YouTubeClient(
        YouTubeAPIConfig(api_key="test-key", base_url="https://example.test"),
        session=session,
        search_throttle_seconds=7.0,
    )

    client.get_videos(["abc123"])

    assert session.calls[0]["url"] == "https://example.test/videos"
