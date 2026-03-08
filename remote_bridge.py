"""Telegram/WhatsApp bridge with WhatsApp->Telegram fallback routing."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

log = logging.getLogger(__name__)


class RemoteBridge:
    def __init__(self, cfg: dict, data_dir: str, store):
        self.cfg = cfg or {}
        self.store = store
        self.enabled = bool(self.cfg.get("enabled", False))
        self.bridge_key = (self.cfg.get("bridge_key") or "").strip()

        self.telegram_token = (self.cfg.get("telegram_bot_token") or "").strip()
        self.telegram_enabled = bool(self.telegram_token)

        self.whatsapp_token = (self.cfg.get("whatsapp_access_token") or "").strip()
        self.whatsapp_phone_number_id = str(self.cfg.get("whatsapp_phone_number_id") or "").strip()
        self.whatsapp_verify_token = (self.cfg.get("whatsapp_verify_token") or "").strip()
        self.whatsapp_enabled = bool(self.whatsapp_token and self.whatsapp_phone_number_id)

        self.default_whatsapp_free_until = (self.cfg.get("default_whatsapp_free_until") or "").strip()

        self._state_path = Path(data_dir) / "bridge_contacts.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text("utf-8"))
                if isinstance(data, dict) and isinstance(data.get("channels"), dict):
                    return data
            except Exception:
                pass
        return {"channels": {}}

    def _save_state(self):
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(self._state, indent=2), "utf-8")

    def verify_bridge_key(self, key: str | None) -> bool:
        if not self.enabled:
            return False
        expected = self.bridge_key
        if not expected:
            return False
        return (key or "").strip() == expected

    def whatsapp_verify(self, mode: str, verify_token: str, challenge: str) -> tuple[bool, str]:
        ok = (
            self.enabled
            and mode == "subscribe"
            and bool(self.whatsapp_verify_token)
            and verify_token == self.whatsapp_verify_token
        )
        return ok, challenge if ok else "forbidden"

    def _channel_contact(self, channel: str) -> dict:
        channels = self._state.setdefault("channels", {})
        return channels.setdefault(channel, {})

    def _find_channel_by_whatsapp(self, wa_user: str) -> str | None:
        channels = self._state.get("channels", {})
        for channel, contact in channels.items():
            if str(contact.get("whatsapp_user_id") or "") == wa_user:
                return channel
        return None

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _is_whatsapp_expired(self, contact: dict) -> bool:
        free_until = (contact.get("whatsapp_free_until") or self.default_whatsapp_free_until or "").strip()
        if not free_until:
            return False
        try:
            # Accept YYYY-MM-DD or full isoformat
            if len(free_until) == 10:
                dt = datetime.fromisoformat(f"{free_until}T23:59:59+00:00")
            else:
                dt = datetime.fromisoformat(free_until)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return self._now_utc() > dt
        except Exception:
            return False

    def _send_json(self, url: str, payload: dict, headers: dict[str, str] | None = None):
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        with request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def _send_telegram(self, chat_id: int | str, text: str):
        if not self.telegram_enabled:
            return
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        self._send_json(url, {"chat_id": chat_id, "text": text[:4000]})

    def _send_whatsapp(self, wa_user_id: str, text: str):
        if not self.whatsapp_enabled:
            return
        url = f"https://graph.facebook.com/v19.0/{self.whatsapp_phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_user_id,
            "type": "text",
            "text": {"body": text[:4000]},
        }
        headers = {"Authorization": f"Bearer {self.whatsapp_token}"}
        self._send_json(url, payload, headers=headers)

    def _channel_for_telegram_chat(self, chat_id: int | str) -> str:
        channels = self._state.get("channels", {})
        sid = str(chat_id)
        for channel, contact in channels.items():
            if str(contact.get("telegram_chat_id") or "") == sid:
                return channel
        return f"remote-tg-{sid}"

    def _handle_telegram_command(self, channel: str, text: str, chat_id: int | str) -> tuple[bool, str | None]:
        msg = text.strip()
        lower = msg.lower()
        contact = self._channel_contact(channel)

        if lower.startswith("/linkwa "):
            wa_user = msg.split(" ", 1)[1].strip()
            if not wa_user:
                return True, "Usage: /linkwa <whatsapp-number-or-id>"
            contact["whatsapp_user_id"] = wa_user
            contact.setdefault("preferred", "telegram")
            self._save_state()
            return True, f"Linked WhatsApp user {wa_user} to channel {channel}."

        if lower.startswith("/wafreeuntil "):
            value = msg.split(" ", 1)[1].strip()
            contact["whatsapp_free_until"] = value
            self._save_state()
            return True, f"Set WhatsApp free-until to {value}."

        if lower.startswith("/prefer "):
            value = msg.split(" ", 1)[1].strip().lower()
            if value not in ("whatsapp", "telegram"):
                return True, "Usage: /prefer telegram|whatsapp"
            contact["preferred"] = value
            self._save_state()
            return True, f"Preferred platform set to {value}."

        if lower.startswith("/channel "):
            new_channel = msg.split(" ", 1)[1].strip().lower().replace(" ", "-")
            if not new_channel:
                return True, "Usage: /channel <name>"
            channels = self._state.setdefault("channels", {})
            old = channels.pop(channel, {})
            channels[new_channel] = old
            channels[new_channel]["telegram_chat_id"] = str(chat_id)
            channels[new_channel]["preferred"] = channels[new_channel].get("preferred", "telegram")
            self._save_state()
            return True, f"Channel changed to {new_channel}."

        if lower.startswith("/help") or lower.startswith("/start"):
            return True, (
                "Commands:\n"
                "/channel <name> - rename your mapped channel\n"
                "/linkwa <wa-id> - link your WhatsApp user id\n"
                "/wafreeuntil YYYY-MM-DD - set WhatsApp free plan end\n"
                "/prefer telegram|whatsapp - set reply destination"
            )

        return False, None

    def ingest_telegram_update(self, update: dict) -> bool:
        if not self.enabled:
            return False
        msg = update.get("message") or update.get("edited_message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return False

        text = (msg.get("text") or "").strip()
        if not text:
            return True

        channel = self._channel_for_telegram_chat(chat_id)
        contact = self._channel_contact(channel)
        contact["telegram_chat_id"] = str(chat_id)
        contact["telegram_username"] = (chat.get("username") or "")
        contact.setdefault("preferred", "telegram")
        contact["last_inbound_platform"] = "telegram"
        self._save_state()

        consumed, reply = self._handle_telegram_command(channel, text, chat_id)
        if consumed:
            if reply:
                try:
                    self._send_telegram(chat_id, reply)
                except Exception:
                    log.exception("telegram command reply failed")
            return True

        sender = f"telegram:{chat.get('username') or chat_id}"
        self.store.add(sender=sender, text=text, channel=channel)
        return True

    def ingest_whatsapp_update(self, payload: dict) -> bool:
        if not self.enabled:
            return False

        entries = payload.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                messages = value.get("messages") or []
                for message in messages:
                    wa_user = str(message.get("from") or "").strip()
                    if not wa_user:
                        continue
                    text = ((message.get("text") or {}).get("body") or "").strip()
                    if not text:
                        continue

                    channel = self._find_channel_by_whatsapp(wa_user) or f"remote-wa-{wa_user}"
                    contact = self._channel_contact(channel)
                    contact["whatsapp_user_id"] = wa_user
                    contact.setdefault("preferred", "whatsapp")
                    contact["last_inbound_platform"] = "whatsapp"
                    self._save_state()

                    sender = f"whatsapp:{wa_user}"
                    self.store.add(sender=sender, text=text, channel=channel)

        return True

    def relay_message(self, msg: dict, known_agents: set[str]):
        if not self.enabled:
            return

        sender = (msg.get("sender") or "").strip()
        channel = (msg.get("channel") or "general").strip()
        text = (msg.get("text") or "").strip()
        msg_type = msg.get("type")

        if not text:
            return
        if sender.startswith("telegram:") or sender.startswith("whatsapp:"):
            return
        if sender not in known_agents and msg_type not in ("system", "session_end"):
            return

        contact = self._state.get("channels", {}).get(channel)
        if not contact:
            return

        out = f"{sender}: {text}"

        preferred = (contact.get("preferred") or "telegram").lower()
        wa_expired = self._is_whatsapp_expired(contact)

        try:
            if preferred == "whatsapp" and not wa_expired and contact.get("whatsapp_user_id") and self.whatsapp_enabled:
                self._send_whatsapp(str(contact["whatsapp_user_id"]), out)
                return

            # Automatic fallback to telegram when WhatsApp free plan expired
            if wa_expired and contact.get("preferred") == "whatsapp":
                contact["preferred"] = "telegram"
                self._save_state()

            tg_chat_id = contact.get("telegram_chat_id")
            if tg_chat_id and self.telegram_enabled:
                self._send_telegram(tg_chat_id, out)
        except error.HTTPError:
            log.exception("bridge outbound HTTP error")
        except Exception:
            log.exception("bridge outbound send failed")
