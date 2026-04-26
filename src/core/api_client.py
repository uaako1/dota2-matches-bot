from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.core.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class APIClient:
    def __init__(
        self,
        cache_dir: str | Path = "data/cache",
        cache_ttl_seconds: int = 24 * 60 * 60,
        connect_timeout: int = 5,
        read_timeout: int = 12,
        user_agent: str = "dota2-matches-bot-next/0.1",
    ):
        self.cache = CacheManager(Path(cache_dir), ttl_seconds=cache_ttl_seconds)
        self.timeout = (int(connect_timeout), int(read_timeout))
        self.user_agent = user_agent
        self.session = None

    def _build_session(self):
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            }
        )
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504, 521, 522, 524),
            allowed_methods=frozenset(["GET", "POST"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def close(self) -> None:
        close = getattr(self.session, "close", None)
        if callable(close):
            close()

    def _ensure_session(self):
        if self.session is None:
            self.session = self._build_session()
        return self.session

    def _request_json_sync(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any | None:
        session = self._ensure_session()
        try:
            response = session.request(
                method.upper(),
                url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 404:
                return None
            content_type = response.headers.get("content-type", "")
            if response.status_code in {401, 403} and "text/html" in content_type:
                logger.warning("API blocked by HTML challenge: %s", url)
                return None
            response.raise_for_status()
            return response.json()
        except ValueError:
            logger.warning("API returned non-JSON response: %s", url)
            return None
        except Exception as exc:
            logger.warning("API request failed for %s: %s", url, exc)
            return None

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
    ) -> Any | None:
        cache_key = self.cache.build_key(url, params=params)
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        data = await asyncio.to_thread(
            self._request_json_sync,
            "GET",
            url,
            params=params,
            headers=headers,
        )
        if use_cache and data is not None:
            self.cache.set(cache_key, data)
        return data

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: dict[str, str] | None = None,
        use_cache: bool = False,
    ) -> Any | None:
        cache_key = self.cache.build_key(url, body=json_body)
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        data = await asyncio.to_thread(
            self._request_json_sync,
            "POST",
            url,
            json_body=json_body,
            headers=headers,
        )
        if use_cache and data is not None:
            self.cache.set(cache_key, data)
        return data
