import logging
import httpx
from typing import Optional, List, Dict, Any, Tuple
from app.config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and len(self.bot_token.strip()) > 5)

    async def verify_bot_token(self, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify if a bot token is valid by querying Telegram's getMe endpoint.
        """
        active_token = (token or self.bot_token or "").strip()
        if not active_token:
            return {"valid": False, "error": "Bot token is empty"}

        url = f"https://api.telegram.org/bot{active_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                data = res.json()
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    return {
                        "valid": True,
                        "bot_username": bot_info.get("username"),
                        "bot_name": bot_info.get("first_name"),
                        "can_join_groups": bot_info.get("can_join_groups", True)
                    }
                else:
                    return {"valid": False, "error": data.get("description", "Invalid bot token")}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def detect_chat_id(self, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Auto-detect the user's Chat ID from recent bot messages via getUpdates.
        """
        active_token = (token or self.bot_token or "").strip()
        if not active_token:
            return {"success": False, "error": "Bot token is missing"}

        url = f"https://api.telegram.org/bot{active_token}/getUpdates"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                data = res.json()
                if not data.get("ok"):
                    return {"success": False, "error": data.get("description", "Failed to query Telegram updates")}

                updates = data.get("result", [])
                if not updates:
                    return {
                        "success": False,
                        "message": "No messages found. Please open your bot in Telegram, tap 'Start' or send 'hello', then try again."
                    }

                # Find the most recent message with chat information
                for u in reversed(updates):
                    msg = u.get("message") or u.get("channel_post") or u.get("edited_message")
                    if msg and "chat" in msg:
                        chat = msg["chat"]
                        return {
                            "success": True,
                            "chat_id": str(chat.get("id")),
                            "username": chat.get("username"),
                            "first_name": chat.get("first_name") or chat.get("title", "User"),
                            "last_message": msg.get("text", "")
                        }

                return {
                    "success": False,
                    "message": "No direct messages found. Please send a message to your bot first."
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_message_detailed(self, text: str, parse_mode: str = "HTML") -> Tuple[bool, str]:
        """
        Send a message and return (success, message_or_error).
        """
        if not self.is_configured():
            return False, "Telegram is not fully configured (bot token or chat ID is missing)."

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                data = res.json()
                if data.get("ok"):
                    logger.info("[Telegram] Successfully delivered message")
                    return True, "Message delivered successfully"
                else:
                    err_desc = data.get("description", "Telegram API error")
                    logger.error(f"[Telegram] Delivery failed: {err_desc}")
                    return False, err_desc
        except Exception as e:
            logger.error(f"[Telegram] Network error sending message: {e}")
            return False, str(e)

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message via Telegram Bot API (backward compatibility).
        """
        success, _ = await self.send_message_detailed(text, parse_mode)
        return success

    async def send_daily_digest(self, ideas: List[Dict[str, Any]]) -> bool:
        """
        Format and dispatch the daily ideas digest.
        """
        if not ideas:
            return False

        lines = [
            "📡 <b>ATH Radar — Daily Content Intelligence</b>",
            f"Here are {len(ideas)} curated ideas ready for you today:\n"
        ]

        for i, idea in enumerate(ideas[:5], 1):
            title = idea.get("title", "Untitled Idea")
            hook = idea.get("hook", "")
            angle = idea.get("angle", "")
            personal = idea.get("personal_connection", "")
            format_type = idea.get("suggested_format", "breakdown")

            lines.append(f"<b>{i}. {title}</b>")
            if hook:
                lines.append(f"🎯 <i>Hook:</i> {hook}")
            if angle:
                lines.append(f"💡 <i>Angle:</i> {angle}")
            if personal:
                lines.append(f"🔗 <i>ATH Connection:</i> {personal}")
            lines.append(f"📝 <i>Format:</i> {format_type}\n")

        lines.append("⚡ <i>Open your ATH Radar dashboard to rewrite, polish, or publish!</i>")
        message = "\n".join(lines)
        return await self.send_message(message)

    async def send_posting_reminder(self, saved_count: int = 0) -> bool:
        """
        Send a reminder to publish or review saved ideas.
        """
        text = (
            "⏰ <b>ATH Radar — Posting Reminder</b>\n\n"
            f"You have <b>{saved_count}</b> high-conviction ideas saved in your queue.\n"
            "Take 5 minutes to polish and publish one today!"
        )
        return await self.send_message(text)

telegram_service = TelegramService()
