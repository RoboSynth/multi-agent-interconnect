from __future__ import annotations

import asyncio
import logging
import random
import ssl
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class GroupAclError(RuntimeError):
    pass


class GroupAclClient:
    def __init__(
        self,
        *,
        base_url: str,
        ssl_context: Optional[ssl.SSLContext] = None,
        timeout: float | httpx.Timeout | None = None,
        trust_env: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 4,
    ) -> None:
        if type(max_attempts) is not int or not 1 <= max_attempts <= 4:
            raise ValueError("max_attempts must be between 1 and 4")
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            verify=ssl_context if ssl_context is not None else True,
            timeout=timeout if timeout is not None else httpx.Timeout(connect=5, read=10, write=10, pool=5),
            trust_env=trust_env,
            transport=transport,
        )

    async def add_member(
        self, *, leader_aic: str, group_id: str, member_aic: str
    ) -> None:
        await self._request(
            "PUT",
            f"/groups/{quote(leader_aic, safe='')}/{quote(group_id, safe='')}"
            f"/members/{quote(member_aic, safe='')}",
        )

    async def remove_member(
        self, *, leader_aic: str, group_id: str, member_aic: str
    ) -> None:
        await self._request(
            "DELETE",
            f"/groups/{quote(leader_aic, safe='')}/{quote(group_id, safe='')}"
            f"/members/{quote(member_aic, safe='')}",
        )

    async def delete_group(self, *, leader_aic: str, group_id: str) -> None:
        await self._request(
            "DELETE",
            f"/groups/{quote(leader_aic, safe='')}/{quote(group_id, safe='')}",
        )

    async def close_member_connection(
        self, *, leader_aic: str, group_id: str, member_aic: str
    ) -> None:
        await self._request(
            "DELETE",
            f"/groups/{quote(leader_aic, safe='')}/{quote(group_id, safe='')}"
            f"/members/{quote(member_aic, safe='')}/connection",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str) -> None:
        logger.info(
            "event=group_acl_client_request method=%s base_url=%s path=%s",
            method,
            self.base_url,
            path,
        )
        # Only the idempotent membership PUT and DELETE operations may retry.
        retryable = method in {"PUT", "DELETE"}
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self._client.request(method, path)
            except httpx.RequestError as exc:
                transient = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout))
                if not (retryable and transient and attempt < self.max_attempts):
                    error = GroupAclError(f"{method} {path} failed: {type(exc).__name__}")
                    error.attempts = attempt
                    error.request_error_class = type(exc).__name__
                    raise error from exc
            else:
                if method == "DELETE" and response.status_code == 404:
                    return
                if not (retryable and response.status_code >= 500 and attempt < self.max_attempts):
                    break
            delay = .5 * (2 ** (attempt - 1)) + random.uniform(0, .1)
            logger.warning("event=group_acl_client_retry method=%s path=%s attempt=%d delay=%.3f",
                           method, path, attempt, delay)
            await asyncio.sleep(delay)
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            logger.error(
                "event=group_acl_client_request_failed method=%s path=%s status=%s detail=%s",
                method,
                path,
                response.status_code,
                detail,
            )
            raise GroupAclError(
                f"{method} {path} failed: {response.status_code} {detail}"
            )
        logger.info(
            "event=group_acl_client_request_done method=%s path=%s status=%s",
            method,
            path,
            response.status_code,
        )
