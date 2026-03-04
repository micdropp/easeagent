"""Feishu (Lark) Bot — sends messages via Webhook and tenant_access_token API.

Supports plain text, interactive cards, and toilet-status cards.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


class FeishuBot:
    """Async Feishu bot client with webhook and API message support."""

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        bot_webhook: str = "",
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._webhook = bot_webhook
        self._tenant_token: str = ""
        self._token_expires: float = 0.0
        self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def available(self) -> bool:
        return bool(self._webhook) or bool(self._app_id and self._app_secret)

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Tenant access token (auto-refresh)
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        if self._tenant_token and time.time() < self._token_expires - 60:
            return self._tenant_token
        if not self._app_id or not self._app_secret:
            return ""
        try:
            resp = await self._http.post(
                TENANT_TOKEN_URL,
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            data = resp.json()
            self._tenant_token = data.get("tenant_access_token", "")
            self._token_expires = time.time() + data.get("expire", 7200)
            logger.info("Feishu tenant_access_token refreshed (expires in %ds)", data.get("expire", 0))
        except Exception:
            logger.exception("Failed to refresh Feishu tenant_access_token")
        return self._tenant_token

    # ------------------------------------------------------------------
    # Webhook (simple, no auth needed)
    # ------------------------------------------------------------------

    async def send_webhook(self, text: str) -> bool:
        if not self._webhook:
            logger.warning("Feishu webhook not configured")
            return False
        try:
            resp = await self._http.post(
                self._webhook,
                json={"msg_type": "text", "content": {"text": text}},
            )
            resp.raise_for_status()
            ok = resp.json().get("code", -1) == 0
            if not ok:
                logger.warning("Feishu webhook returned: %s", resp.text[:300])
            return ok
        except Exception:
            logger.exception("Feishu webhook send failed")
            return False

    async def send_webhook_card(self, card: dict[str, Any]) -> bool:
        if not self._webhook:
            return False
        try:
            resp = await self._http.post(
                self._webhook,
                json={"msg_type": "interactive", "card": card},
            )
            return resp.json().get("code", -1) == 0
        except Exception:
            logger.exception("Feishu webhook card send failed")
            return False

    # ------------------------------------------------------------------
    # API message (requires app_id / app_secret)
    # ------------------------------------------------------------------

    async def send_message(
        self,
        receive_id: str,
        content: str,
        msg_type: str = "text",
        receive_id_type: str = "user_id",
    ) -> bool:
        token = await self._ensure_token()
        if not token:
            logger.warning("No Feishu token, falling back to webhook")
            return await self.send_webhook(content)
        try:
            resp = await self._http.post(
                SEND_MESSAGE_URL,
                params={"receive_id_type": receive_id_type},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": receive_id,
                    "msg_type": msg_type,
                    "content": content,
                },
            )
            data = resp.json()
            if data.get("code", -1) != 0:
                logger.warning("Feishu send_message error: %s", data.get("msg"))
                return False
            return True
        except Exception:
            logger.exception("Feishu send_message failed")
            return False

    # ------------------------------------------------------------------
    # High-level helpers used by tool_executor
    # ------------------------------------------------------------------

    async def notify(
        self,
        employee_id: str,
        message: str,
        msg_type: str = "text",
    ) -> dict[str, Any]:
        """Send notification to employee. Returns result dict for tool_executor."""
        if msg_type == "card":
            card = self._build_notification_card(employee_id, message)
            ok = await self.send_webhook_card(card)
        elif msg_type == "toilet_status":
            card = self._build_toilet_card(message)
            ok = await self.send_webhook_card(card)
        else:
            ok = await self.send_webhook(f"[EaseAgent] {employee_id}: {message}")

        return {
            "notified": employee_id,
            "message": message,
            "sent": ok,
            "channel": "feishu",
        }

    # ------------------------------------------------------------------
    # Card templates
    # ------------------------------------------------------------------

    @staticmethod
    def _build_notification_card(employee_id: str, message: str) -> dict[str, Any]:
        return {
            "header": {
                "title": {"tag": "plain_text", "content": "EaseAgent 通知"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**对象**: {employee_id}\n**内容**: {message}",
                    },
                },
            ],
        }

    @staticmethod
    def _build_toilet_card(message: str) -> dict[str, Any]:
        return {
            "header": {
                "title": {"tag": "plain_text", "content": "厕位状态更新"},
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": message},
                },
            ],
        }
