"""Hermes Gateway client.

Talks to the Hermes Agent OpenAI-compatible API Server (the "gateway"), which
runs the agent loop / tools / memory behind a `/chat/completions` endpoint.
Adapted (trimmed) from ai_driven_rtl/src/hermes_engine.py: a single shared
httpx client with keep-alive, sync + async run, and a small transient-error
backoff.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

_TRANSIENT = (429, 500, 502, 503, 504)

_shared_client: Optional[httpx.Client] = None
_shared_client_lock = threading.Lock()


def _get_shared_client(timeout: float) -> httpx.Client:
    global _shared_client
    if _shared_client is not None:
        return _shared_client
    with _shared_client_lock:
        if _shared_client is None:
            _shared_client = httpx.Client(
                timeout=timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                headers={"Connection": "keep-alive"},
            )
    return _shared_client


def close_shared_client() -> None:
    global _shared_client
    with _shared_client_lock:
        if _shared_client is not None:
            _shared_client.close()
            _shared_client = None


@dataclass
class HermesResponse:
    content: str
    raw: Dict[str, Any]


class HermesGateway:
    """Minimal adapter over the Hermes Gateway `/chat/completions` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "hermes-agent",
        instructions: str = "",
        timeout: float = 600.0,
        name: str = "rtl-assistant",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.instructions = instructions
        self.timeout = timeout
        self.name = name

    def _payload(self, prompt: str) -> Dict[str, Any]:
        messages = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        messages.append({"role": "user", "content": prompt})
        return {"model": self.model, "messages": messages, "stream": False}

    def _headers(self, user_id: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Hermes-Session-Key": f"hls-rtl:{self.name}:{user_id}",
            "X-Hermes-Session-Id": f"{self.name}-{user_id}",
        }

    async def run_async(self, prompt: str, user_id: str = "default-user") -> HermesResponse:
        if not self.api_key:
            raise RuntimeError("HERMES_GATEWAY_API_KEY is missing")
        url = f"{self.base_url}/chat/completions"
        payload, headers = self._payload(prompt), self._headers(user_id)
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                ) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code in _TRANSIENT and attempt < 2:
                        last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                        await asyncio.sleep(0.4 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                content = self._extract_content(data)
                if not content:
                    raise RuntimeError(f"Hermes Gateway returned no content: {data}")
                return HermesResponse(content=content, raw=data)
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:1000] if exc.response is not None else ""
                raise RuntimeError(
                    f"Hermes Gateway returned HTTP {exc.response.status_code}: {body}"
                ) from exc
        raise last_exc or RuntimeError("Hermes Gateway call failed after retries")

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> Optional[str]:
        choices = data.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content.strip()
        return None
