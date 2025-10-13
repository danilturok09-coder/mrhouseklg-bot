"""
ops_agent.py — оператор для бота Mr.House

Что умеет:
1) Проверяет Telegram токен (getMe).
2) Смотрит статус вебхука (getWebhookInfo).
3) Проверяет Render (GET / и /version).
4) Ставит/чинит вебхук (setWebhook), если нужно.
5) Триггерит деплой на Render (Deploy Hook или Render API).
6) Может запускать workflow ops.yml через GitHub API (режим агента).

Все секреты храним в GitHub → Settings → Secrets and variables → Actions.
Ничего секретного в код не вставляем.
"""

import os
import sys
import json
import argparse
import datetime
import requests

# === Переменные окружения (берутся из GitHub Secrets) ========================

# Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")               # токен из @BotFather
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")     # https://<service>.onrender.com
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")     # придуманный секрет (строка)

# Render — любой один способ (или оба)
RENDER_DEPLOY_HOOK = os.environ.get("RENDER_DEPLOY_HOOK", "")  # URL из Settings → Deploy Hooks
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "")          # Account settings → API Keys
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")    # Service → Settings → Service ID

# GitHub token для удалённого запуска workflow (имя секрета НЕ должно начинаться с GITHUB_)
MY_GITHUB_TOKEN = os.environ.get("MY_GITHUB_TOKEN", "")        # Personal Access Token с правами repo, workflow

TG = f"https://api.telegram.org/bot{BOT_TOKEN}"


# === Утилита красивого вывода в логи ========================================
def pretty(title, payload):
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


# === Telegram: проверки и операции ==========================================
def get_me():
    try:
        r = requests.get(f"{TG}/getMe", timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def get_webhook_info():
    try:
        r = requests.get(f"{TG}/getWebhookInfo", timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def set_webhook():
    url = f"{BASE_URL}/webhook"
    data = {"url": url, "secret_token": WEBHOOK_SECRET}
    try:
        r = requests.post(f"{TG}/setWebhook", data=data, timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def delete_webhook():
    try:
        r = requests.post(f"{TG}/deleteWebhook", timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


# === Render: проверки и деплой ==============================================
def health_check():
    results = {}
    for path in ["/", "/version"]:
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get
