from __future__ import annotations

from typing import Any

from src.core.api_client import APIClient

_client: APIClient | None = None


def get_shared_api_client() -> APIClient:
    global _client
    if _client is None:
        _client = APIClient(user_agent="DotaWatchBot/2.1 contact:telegram:@dotawatch")
    return _client


def request(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | tuple[int, int] | None = None,
):
    return get_shared_api_client().request_sync(
        method,
        url,
        params=params,
        json_body=json_body,
        headers=headers,
        timeout=timeout,
    )


def get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout=None):
    return request("GET", url, params=params, headers=headers, timeout=timeout)


def post_json(url: str, *, json_body: dict[str, Any], headers: dict[str, str] | None = None, timeout=None):
    return request("POST", url, json_body=json_body, headers=headers, timeout=timeout)
