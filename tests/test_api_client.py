from __future__ import annotations

import unittest
from pathlib import Path

from src.core.api_client import APIClient


class MemoryCache:
    def __init__(self) -> None:
        self.data = {}

    @staticmethod
    def build_key(url: str, params=None, body=None):
        return url

    def get(self, key):
        return self.data.get(key)

    def set(self, key, data):
        self.data[key] = data


class APIClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_uses_cache_after_first_fetch(self) -> None:
        client = APIClient(cache_dir=Path("data/test-cache-api-client-memory"))
        client.cache = MemoryCache()  # type: ignore[assignment]
        calls: list[str] = []

        def fake_request(method: str, url: str, **kwargs):
            calls.append(url)
            return {"ok": True, "url": url}

        client._request_json_sync = fake_request  # type: ignore[method-assign]

        first = await client.get("https://example.test/data")
        second = await client.get("https://example.test/data")

        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    async def test_post_passes_per_request_headers(self) -> None:
        client = APIClient(cache_dir=Path("data/test-cache-api-client-headers"))
        seen_headers = None

        def fake_request(method: str, url: str, **kwargs):
            nonlocal seen_headers
            seen_headers = kwargs.get("headers")
            return {"ok": True}

        client._request_json_sync = fake_request  # type: ignore[method-assign]

        result = await client.post(
            "https://example.test/graphql",
            json_body={"query": "{}"},
            headers={"Authorization": "Bearer token"},
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(seen_headers, {"Authorization": "Bearer token"})
