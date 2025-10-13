"""
ops_agent.py — «оператор» для бота Mr.House

Задача: по кнопке в GitHub Actions (workflow_dispatch) проверить и при необходимости
починить интеграцию Telegram ↔ Render, а также инициировать деплой.

Что делает:
1) Проверяет токен Telegram (getMe).
2) Смотрит состояние вебхука (getWebhookInfo).
3) Проверяет здоровье вашего сервиса на Render (GET / и /version).
4) Если надо — ставит/чинит вебхук (setWebhook).
5) По желанию — инициирует деплой на Render (Deploy Hook или Render API).
6) Печатает понятный SUMMARY со статусами.

Как запускать:
- В репозитории есть .github/workflows/ops.yml (см. инструкцию).
- В GitHub → Actions → MrHouse Ops Agent → Run workflow → action = full/diagnose/...

Где хранятся значения:
- Все чувствительные данные (токены, ключи) кладём только в GitHub Secrets (Settings → Secrets → Actions).
"""

import os
import json
import argparse
import requests
import datetime

# === Переменные окружения (берутся из GitHub Secrets) ========================

# Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")               # токен из @BotFather
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")     # домен Render: https://<service>.onrender.com
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")     # любой придуманный «секрет» для защиты вебхука

# Render — два способа перезапускать деплой (любой один, или оба):
RENDER_DEPLOY_HOOK = os.environ.get("RENDER_DEPLOY_HOOK", "")  # готовый URL «Deploy Hook» из настроек сервиса
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "")          # личный API key аккаунта Render
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")    # ID конкретного сервиса на Render

# Базовый URL Telegram API для вашего бота
TG = f"https://api.telegram.org/bot{BOT_TOKEN}"


# === Утилита красивого вывода в логи GitHub Actions =========================
def pretty(title, payload):
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


# === Telegram: проверки и операции ==========================================
def get_me():
    """Проверяем валидность токена, видим username бота."""
    try:
        r = requests.get(f"{TG}/getMe", timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def get_webhook_info():
    """Смотрим, установлен ли вебхук и куда именно он указывает."""
    try:
        r = requests.get(f"{TG}/getWebhookInfo", timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def set_webhook():
    """
    Ставим/обновляем вебхук.
    Telegram будет присылать апдейты на BASE_URL + /webhook
    и добавлять заголовок X-Telegram-Bot-Secret-Token со значением WEBHOOK_SECRET.
    """
    url = f"{BASE_URL}/webhook"
    data = {"url": url, "secret_token": WEBHOOK_SECRET}
    try:
        r = requests.post(f"{TG}/setWebhook", data=data, timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def delete_webhook():
    """На всякий случай — удалить вебхук (не используется в full, но полезно иметь)."""
    try:
        r = requests.post(f"{TG}/deleteWebhook", timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


# === Render: проверки и деплой ==============================================
def health_check():
    """
    Проверяем, отвечает ли сервис на Render:
    - GET /            -> 200 ОК (обычно health или главная)
    - GET /version     -> 200 ОК (если реализован эндпоинт версии)
    """
    results = {}
    for path in ["/", "/version"]:
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get(url, timeout=15)
            results[path] = (r.status_code, r.text[:200])
        except Exception as e:
            results[path] = (0, str(e))
    return results


def render_redeploy():
    """
    Инициируем деплой на Render одним из способов:
    1) Deploy Hook (проще всего): просто POST на заранее выданный Render URL.
    2) Render API: POST /v1/services/{SERVICE_ID}/deploys с Authorization: Bearer <API_KEY>.

    Возвращаем кортеж: (mode, status_code, response_text[:N])
    """
    if RENDER_DEPLOY_HOOK:
        try:
            r = requests.post(RENDER_DEPLOY_HOOK, timeout=20)
            return ("deploy_hook", r.status_code, r.text[:400])
        except Exception as e:
            return ("deploy_hook", 0, str(e))
    elif RENDER_API_KEY and RENDER_SERVICE_ID:
        headers = {
            "Authorization": f"Bearer {RENDER_API_KEY}",
            "Accept": "application/json"
        }
        try:
            r = requests.post(
                f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys",
                headers=headers,
                json={"clearCache": True},
                timeout=20
            )
            return ("api", r.status_code, r.text[:400])
        except Exception as e:
            return ("api", 0, str(e))
    else:
        return ("none", 0, "No Render credentials provided.")


# === Основной сценарий агента ===============================================
def main(action: str):
    """
    action:
      - diagnose   -> только проверить (без изменений)
      - fix-webhook-> проверить и поставить вебхук при необходимости
      - redeploy   -> инициировать деплой Render (если есть хук/ключи)
      - full       -> всё сразу: diagnose + fix-webhook + redeploy
    """
    problems = []

    # 1) Проверка Telegram токена
    sc_me, me = get_me()
    pretty("Telegram getMe", {"status_code": sc_me, "body": me})
    me_ok = (sc_me == 200 and isinstance(me, dict) and me.get("ok") is True)
    if not me_ok:
        problems.append("TELEGRAM_TOKEN_INVALID")

    # 2) Состояние вебхука
    sc_wh, wh = get_webhook_info()
    pretty("Telegram getWebhookInfo", {"status_code": sc_wh, "body": wh})

    webhook_url = ""
    if isinstance(wh, dict) and wh.get("ok") and isinstance(wh.get("result"), dict):
        webhook_url = wh["result"].get("url", "") or ""

    # 3) Проверки здоровья Render
    hc = health_check()
    pretty("Render health", hc)

    # 4) Починка вебхука (если выбрано)
    if action in ("fix-webhook", "full"):
        need_set = False
        # если вебхука нет или он указывает не на наш BASE_URL — поставим
        if not webhook_url:
            need_set = True
        elif BASE_URL and not webhook_url.startswith(BASE_URL):
            need_set = True

        if need_set:
            # ставим вебхук только если есть всё необходимое
            if BOT_TOKEN and BASE_URL and WEBHOOK_SECRET:
                sc_set, res_set = set_webhook()
                pretty("setWebhook", {"status_code": sc_set, "body": res_set})
                if not (sc_set == 200 and isinstance(res_set, dict) and res_set.get("ok")):
                    problems.append("SET_WEBHOOK_FAILED")
            else:
                problems.append("MISSING_ENV_FOR_WEBHOOK")  # нет BOT_TOKEN/BASE_URL/WEBHOOK_SECRET
        else:
            print("Webhook looks OK — no changes.")

    # 5) Деплой (если выбрано)
    if action in ("redeploy", "full"):
        mode, sc_dep, res_dep = render_redeploy()
        pretty("Render redeploy", {"mode": mode, "status_code": sc_dep, "body": res_dep})
        if mode == "none":
            print("ℹ️ Добавь RENDER_DEPLOY_HOOK или (RENDER_API_KEY + RENDER_SERVICE_ID) в GitHub Secrets.")

    # 6) Итоговый отчёт
    summary = {
        "me_ok": me_ok,
        "webhook": webhook_url,
        "health_root": hc.get("/", (0, ""))[0],
        "health_version": hc.get("/version", (0, ""))[0],
        "problems": problems,
        "checked_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    pretty("SUMMARY", summary)


# === Точка входа ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action",
        default="full",
        help="diagnose | fix-webhook | redeploy | full"
    )
    args = parser.parse_args()
    main(args.action)
    # === РЕЖИМ АГЕНТА: обработка внешних команд ===
import sys
import requests

def agent_command(action: str):
    """
    Позволяет вызывать команды прямо через GitHub Actions API.
    Пример: agent_command('full') или agent_command('redeploy')
    """
    repo = "danilturok09-coder/mrhouseklg-bot"  # ← твой репозиторий
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("❌ Нет GitHub токена. Добавь его в Secrets как GITHUB_TOKEN.")
        return

    url = f"https://api.github.com/repos/{repo}/actions/workflows/ops.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "ref": "main",
        "inputs": {"action": action}
    }
    r = requests.post(url, headers=headers, json=data)
    print(f"Запрос к GitHub Actions отправлен: {r.status_code} → {r.text}")

# === Автозапуск, если передан параметр командой ===
if len(sys.argv) > 1 and sys.argv[1] in ["full", "redeploy", "fix-webhook", "diagnose"]:
    agent_command(sys.argv[1])
