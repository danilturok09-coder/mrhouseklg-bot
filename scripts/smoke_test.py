# scripts/smoke_test.py
# ------------------------------------------------------------------------------
# Проверяет, что Render и Telegram бот живы
# ------------------------------------------------------------------------------

import os
import requests
import time
import sys

BASE_URL = os.environ["BASE_URL"].rstrip("/")
BOT_TOKEN = os.environ["BOT_TOKEN"]

def wait_ok(url, tries=10, delay=5):
    for _ in range(tries):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False

print("🩺 Проверяю Render...")
ok_root = wait_ok(f"{BASE_URL}/")
if not ok_root:
    print("❌ Render не отвечает на /")
    sys.exit(1)
else:
    print("✅ Render OK")

print("🤖 Проверяю Telegram API...")
r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
if '"ok":true' in r.text:
    print("✅ Telegram бот активен")
else:
    print("❌ Ошибка Telegram API:", r.text)
    sys.exit(2)
