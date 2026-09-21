"""Telegram bot command listener for linking farmer chat IDs."""

import html
import logging
import threading
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class TelegramBotPoller:
    """Long-poll Telegram updates and reply with the sender's chat ID."""

    def __init__(self, bot_token: str, poll_timeout: int = 25):
        self.bot_token = bot_token.strip()
        self.poll_timeout = poll_timeout
        self.offset: Optional[int] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token)

    def start(self) -> None:
        if not self.enabled:
            logger.info("[Telegram Bot] No bot token configured; command listener disabled")
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll,
            name="telegram-bot-poller",
            daemon=True,
        )
        self._thread.start()
        logger.info("[Telegram Bot] Command listener started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def _poll(self) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        while not self._stop_event.is_set():
            try:
                response = requests.get(
                    url,
                    params={
                        "timeout": self.poll_timeout,
                        **({"offset": self.offset} if self.offset is not None else {}),
                    },
                    timeout=self.poll_timeout + 5,
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    logger.error("[Telegram Bot] getUpdates failed: %s", payload)
                    self._stop_event.wait(5)
                    continue

                for update in payload.get("result", []):
                    self.offset = update.get("update_id", 0) + 1
                    self.handle_update(update)
            except requests.RequestException as exc:
                logger.warning("[Telegram Bot] Polling failed: %s", exc)
                self._stop_event.wait(5)
            except Exception:
                logger.exception("[Telegram Bot] Unexpected polling error")
                self._stop_event.wait(5)

    def handle_update(self, update: dict[str, Any]) -> bool:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return False

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        if chat_id is None or not text:
            return False

        command = text.split()[0].split("@", 1)[0].lower()
        if command not in {"/start", "/id"}:
            return False

        safe_chat_id = html.escape(str(chat_id))
        reply = (
            "Welcome to AgriTech 🌱\n\n"
            f"Your Telegram ID is: <b>{safe_chat_id}</b>\n\n"
            "Use this ID in your farmer registration form so approved credentials can be sent here."
        )
        return self.send_message(chat_id, reply)

    def send_message(self, chat_id: Any, text: str) -> bool:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            payload = response.json()
            if response.ok and payload.get("ok") is True:
                logger.info("[Telegram Bot] Sent chat ID reply to %s", chat_id)
                return True
            logger.error("[Telegram Bot] sendMessage failed: %s", payload)
        except (requests.RequestException, ValueError) as exc:
            logger.error("[Telegram Bot] Could not send message: %s", exc)
        return False
