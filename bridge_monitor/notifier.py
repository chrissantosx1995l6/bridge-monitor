import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)


class Notifier:
    """Dispatches alerts to Telegram and external webhooks when checks fail."""

    def __init__(self, bot_token: str = "", chat_id: str = "", webhook_url: str = ""):
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.webhook_url = webhook_url.strip()
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send_telegram(self, text: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        for attempt in range(2):
            try:
                resp = await self._client.post(url, json=payload)
                if resp.status_code == 429:
                    # Hit rate limit, usually 30 msg/sec overall or 1 msg/sec per chat
                    retry_after = int(resp.headers.get("Retry-After", 3))
                    logger.warning("telegram 429, sleeping %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                if resp.status_code != 200:
                    logger.error("telegram api error (%d): %s", resp.status_code, resp.text)
                    return False
                return True
            except httpx.RequestError as e:
                logger.error("network error sending telegram alert (attempt %d): %s", attempt + 1, e)
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error("failed to send telegram alert: %s", e)
                return False
        return False

    async def send_generic_webhook(self, data: dict) -> bool:
        if not self.webhook_url:
            return False
        try:
            # print(f"DEBUG webhook payload: {data}")
            r = await self._client.post(self.webhook_url, json=data)
            return r.status_code in (200, 201, 202, 204)
        except Exception as e:
            logger.error("failed to dispatch generic webhook: %s", e)
            return False

    async def notify_state_change(self, target_name: str, target_url: str, is_up: bool, reason: str = "", latency_ms: float = 0.0):
        if is_up:
            icon = "🟢"
            status = "RECOVERED"
            details = f"Latency: {latency_ms:.1f}ms"
        else:
            icon = "🔴"
            status = "DOWN"
            details = f"Reason: {reason}" if reason else "Endpoint unreachable"

        # Legacy escape for target names that might contain angle brackets
        safe_name = target_name.replace("<", "&lt;").replace(">", "&gt;")
        safe_details = reason.replace("<", "&lt;").replace(">", "&gt;") if reason else "Endpoint unreachable"
        if is_up:
            safe_details = details

        msg = (
            f"{icon} <b>{safe_name}</b> is {status}\n"
            f"URL: <code>{target_url}</code>\n"
            f"{safe_details}"
        )

        await self.send_telegram(msg)

        if self.webhook_url:
            payload = {
                "event": "state_change",
                "target": target_name,
                "url": target_url,
                "status": status.lower(),
                "latency_ms": round(latency_ms, 2),
                "reason": reason,
            }
            await self.send_generic_webhook(payload)

    async def close(self):
        await self._client.aclose()
