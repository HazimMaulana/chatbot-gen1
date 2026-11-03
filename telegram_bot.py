"""Adapter Telegram long polling -> Flask /chat. Jalankan satu instance per token."""

import logging
import os
from pathlib import Path
import time
import threading
from contextlib import contextmanager

import requests

from config import Config

log = logging.getLogger(__name__)
HELP = ("Halo! Aku Gudi, asisten virtual toko ini. "
        "Ada yang lagi kamu cari, atau mau cerita kebutuhanmu dulu?\n"
        "Informasi barang saat ini masih memakai data contoh.")



class TelegramError(Exception):
    pass


class TelegramBot:
    def __init__(self, token, api_url, state_file, allowed_users=()):
        self.url = f"https://api.telegram.org/bot{token}"
        self.api_url = api_url.rstrip("/")
        self.state_file = Path(state_file)
        self.allowed_users = set(allowed_users)
        self.session = requests.Session()

    def call(self, method, payload=None, timeout=30):
        # Jangan log URL/exception requests: URL Telegram memuat token.
        try:
            response = self.session.post(
                f"{self.url}/{method}", json=payload or {}, timeout=(5, timeout)
            )
            data = response.json()
            if not response.ok or not data.get("ok"):
                raise TelegramError(f"Telegram {method} gagal (HTTP {response.status_code}).")
            return data["result"]
        except (requests.RequestException, ValueError, KeyError):
            raise TelegramError(f"Koneksi Telegram {method} gagal.") from None

    def get_reply(self, text, session_id=None):
        try:
            response = self.session.post(
                f"{self.api_url}/chat", json={"message": text, "session_id": session_id}, timeout=(5, 200)
            )
            data = response.json()
            if response.ok and isinstance(data.get("reply"), str):
                return data["reply"]
            if response.status_code == 400:
                return "Pesan terlalu panjang atau tidak valid. Sebutkan nama barang atau SKU."
        except (requests.RequestException, ValueError):
            pass
        return "Layanan gudang belum bisa diakses. Silakan coba lagi nanti."

    @contextmanager
    def typing(self, chat_id):
        stopped = threading.Event()

        def show_typing():
            # Session terpisah karena requests.Session utama dipakai request Flask.
            with requests.Session() as session:
                while not stopped.is_set():
                    try:
                        session.post(f"{self.url}/sendChatAction", json={
                            "chat_id": chat_id, "action": "typing"}, timeout=(3, 3))
                    except requests.RequestException:
                        pass
                    if stopped.wait(4):
                        break

        worker = threading.Thread(target=show_typing, daemon=True)
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join(timeout=1)

    def handle_update(self, update):
        message = update.get("message", {})
        chat = message.get("chat", {})
        if chat.get("type") != "private" or message.get("from", {}).get("is_bot"):
            return
        user_id = message.get("from", {}).get("id")
        if self.allowed_users and user_id not in self.allowed_users:
            log.info("Pesan diabaikan: pengguna tidak masuk daftar akses.")
            return
        log.info("Pesan private diterima; menyiapkan balasan.")
        text = message.get("text", "").strip()
        if text == "/whoami":
            reply = f"Telegram user ID kamu: {user_id}"
        elif text.split(" ")[0].split("@")[0] in ("/start", "/help") or text.lower() == "menu utama":
            reply = HELP
        elif not text:
            reply = "Kirim pesan teks berisi nama barang atau SKU."
        elif len(text) > Config.MAX_MESSAGE_CHARS:
            reply = f"Pesan maksimal {Config.MAX_MESSAGE_CHARS} karakter."
        else:
            with self.typing(chat["id"]):
                reply = self.get_reply(text, session_id=f"telegram:{user_id}")
        for index in range(0, len(reply), 4000):
            self.call("sendMessage", {"chat_id": chat["id"], "text": reply[index:index + 4000],
                      "reply_markup": {"remove_keyboard": True}})
        log.info("Balasan Telegram berhasil dikirim.")

    def save_offset(self, offset):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(str(offset), encoding="utf-8")
        temporary.replace(self.state_file)

    def run(self):
        me = self.call("getMe")
        log.info("Bot @%s siap. Ctrl+C untuk berhenti.", me["username"])
        if self.call("getWebhookInfo").get("url"):
            raise TelegramError("Webhook masih aktif. Hapus webhook sebelum memakai long polling.")
        offset = int(self.state_file.read_text()) if self.state_file.exists() else 0
        while True:
            try:
                updates = self.call("getUpdates", {
                    "offset": offset, "timeout": 25, "limit": 10,
                    "allowed_updates": ["message"],
                }, timeout=35)
                for update in updates:
                    self.handle_update(update)
                    offset = update["update_id"] + 1
                    self.save_offset(offset)
            except TelegramError as exc:
                log.warning("%s Mencoba lagi dalam 5 detik.", exc)
                time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Isi TELEGRAM_BOT_TOKEN di .env terlebih dahulu.")
    try:
        allowed = [int(value.strip()) for value in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if value.strip()]
    except ValueError:
        raise SystemExit("TELEGRAM_ALLOWED_USER_IDS harus berupa angka dipisahkan koma.") from None
    bot = TelegramBot(
        token, os.getenv("CHAT_API_URL", "http://127.0.0.1:5000"),
        os.getenv("TELEGRAM_STATE_FILE", "data/telegram_offset.txt"), allowed,
    )
    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("Bot dihentikan.")
    except TelegramError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
