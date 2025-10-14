# scripts/notify.py
# ------------------------------------------------------------------------------
# Отправляет сообщение в твой Telegram (админ-чат) о статусе деплоя/проверок.
# ------------------------------------------------------------------------------

import os
import sys
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_ADMIN_CHAT_ID"]  # число (узнай у @userinfobot)

def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "No message"
    r = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        params={"chat_id": CHAT_ID, "text": text},
        timeout=15,
    )
    print("📨 Notify:", r.status_code, r.text)

if name == "__main__":
    main()
