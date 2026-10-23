"""A small client of Telegram's Bot API (https://core.telegram.org/bots/api): long polling and messages with buttons.

Outbound HTTPS only, like everything on the agents' host. The token lives in ``/etc/smartflow/telegram.env`` and
never reaches a log: an error names the method, never the URL (which carries the token).
"""

from __future__ import annotations

import json

from ..net import HttpError, request_json


class TelegramError(Exception):
    def __init__(self, method: str, status: int, text: str):
        super().__init__(f"Telegram {method}: HTTP {status} {text[:200]}")
        self.method, self.status, self.text = method, status, text


class Telegram:
    def __init__(self, token: str, http=request_json):
        if not token or ":" not in token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set (on the host: /etc/smartflow/telegram.env)")
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = http

    def call(self, method: str, _timeout: float = 20, **params) -> dict | list | bool:
        body = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
        try:
            _, doc, _ = self._http("POST", f"{self._base}/{method}", body=body, headers={"Content-Type": "application/json"},
                                   timeout=_timeout, retries=0 if method == "getUpdates" else 2, retry_non_idempotent=method != "sendMessage")
        except HttpError as e:   # the URL holds the token: keep only the method, the status and Telegram's answer
            raise TelegramError(method, e.status, e.body) from None
        if not isinstance(doc, dict) or not doc.get("ok"):
            raise TelegramError(method, 200, json.dumps(doc)[:200])
        return doc.get("result")

    def me(self) -> dict:
        return self.call("getMe")

    def updates(self, offset: int, wait: int = 25) -> list[dict]:
        return self.call("getUpdates", _timeout=wait + 10, offset=offset, timeout=wait, allowed_updates=["message", "callback_query"]) or []

    def send(self, chat: int | str, text: str, buttons: list[list[dict]] | None = None, silent: bool = False) -> dict:
        return self.call("sendMessage", chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview=True,
                         disable_notification=silent or None, reply_markup={"inline_keyboard": buttons} if buttons else None)

    def edit(self, chat: int | str, message_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        try:
            self.call("editMessageText", chat_id=chat, message_id=message_id, text=text, parse_mode="HTML",
                      disable_web_page_preview=True, reply_markup={"inline_keyboard": buttons} if buttons else None)
        except TelegramError as e:
            if "message is not modified" not in e.text:
                raise

    def answer(self, callback_id: str, text: str | None = None) -> None:
        self.call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def commands(self, lang: str | None, items: list[tuple[str, str]]) -> None:
        self.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in items], language_code=lang)
