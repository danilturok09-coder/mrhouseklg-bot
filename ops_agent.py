"""
MrHouse Ops Agent — проверка и починка бота

Секреты (GitHub → Settings → Secrets → Actions):
- BOT_TOKEN
- BASE_URL                  (без завершающего /)
- WEBHOOK_SECRET
- RENDER_DEPLOY_HOOK        (или пара RENDER_API_KEY + RENDER_SERVICE_ID)
- MY_GITHUB_TOKEN           (опционально; для удалённого запуска workflow)
"""

import os
import sys
import json
import argparse
import datetime
import requests

# === ENV ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

RENDER_DEPLOY_HOOK = os.environ.get("RENDER_DEPLOY_HOOK", "")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")

MY_GITHUB_TOKEN = os.environ.get("MY_GITHUB_TOKEN", "")

TG = f"https://api.telegram.org/bot{BOT_TOKEN}"


def pretty(title, payload):
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


# ---------------- Telegram ----------------
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
    try:
        r = requests.post(
            f"{TG}/setWebhook",
            data={"url": url, "secret_token": WEBHOOK_SECRET},
            timeout=20,
        )
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


# ---------------- Render ----------------
def health_check():
    res = {}
    for path in ["/", "/version"]:
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get(url, timeout=15)
            res[path] = (r.status_code, r.text[:200])
        except Exception as e:
            res[path] = (0, str(e))
    return res


def render_redeploy():
    if RENDER_DEPLOY_HOOK:
        try:
            r = requests.post(RENDER_DEPLOY_HOOK, timeout=20)
            return ("deploy_hook", r.status_code, r.text[:400])
        except Exception as e:
            return ("deploy_hook", 0, str(e))
    if RENDER_API_KEY and RENDER_SERVICE_ID:
        try:
            r = requests.post(
                f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys",
                headers={
                    "Authorization": f"Bearer {RENDER_API_KEY}",
                    "Accept": "application/json",
                },
                json={"clearCache": True},
                timeout=20,
            )
            return ("api", r.status_code, r.text[:400])
        except Exception as e:
            return ("api", 0, str(e))
    return ("none", 0, "No Render credentials provided.")


# ---------------- Main flow ----------------
def run_ops(action: str):
    problems = []

    sc_me, me = get_me()
    pretty("Telegram getMe", {"status_code": sc_me, "body": me})
    me_ok = (sc_me == 200 and isinstance(me, dict) and me.get("ok") is True)
    if not me_ok:
        problems.append("TELEGRAM_TOKEN_INVALID")

    sc_wh, wh = get_webhook_info()
    pretty("Telegram getWebhookInfo", {"status_code": sc_wh, "body": wh})
    webhook_url = ""
    if isinstance(wh, dict) and wh.get("ok") and isinstance(wh.get("result"), dict):
        webhook_url = wh["result"].get("url") or ""

    hc = health_check()
    pretty("Render health", hc)

    if action in ("fix-webhook", "full"):
        need_set = False
        if not webhook_url:
            need_set = True
        elif BASE_URL and not webhook_url.startswith(BASE_URL):
            need_set = True

        if need_set:
            if BOT_TOKEN and BASE_URL and WEBHOOK_SECRET:
                sc_set, res_set = set_webhook()
                pretty("setWebhook", {"status_code": sc_set, "body": res_set})
                if not (sc_set == 200 and isinstance(res_set, dict) and res_set.get("ok")):
                    problems.append("SET_WEBHOOK_FAILED")
            else:
                problems.append("MISSING_ENV_FOR_WEBHOOK")

    if action in ("redeploy", "full"):
        mode, sc_dep, res_dep = render_redeploy()
        pretty("Render redeploy", {"mode": mode, "status_code": sc_dep, "body": res_dep})

    summary = {
        "me_ok": me_ok,
        "webhook": webhook_url or "",
        "health_root": hc.get("/", (0, ""))[0],
        "health_version": hc.get("/version", (0, ""))[0],
        "problems": problems,
        "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    pretty("SUMMARY", summary)


# -------- optional: trigger workflow remotely --------
def agent_command(action: str):
    repo = "danilturok09-coder/mrhouseklg-bot"
    if not MY_GITHUB_TOKEN:
        print("⚠️  No MY_GITHUB_TOKEN provided; skip remote trigger.")
        return
    url = f"https://api.github.com/repos/{repo}/actions/workflows/ops.yml/dispatches"
    headers = {"Authorization": f"Bearer {MY_GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    data = {"ref": "main", "inputs": {"action": action}}
    r = requests.post(url, headers=headers, json=data, timeout=20)
    print(f"Remote trigger: {r.status_code} → {r.text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", default="full", help="diagnose | fix-webhook | redeploy | full")
    args = parser.parse_args()
    run_ops(args.action)

    if len(sys.argv) > 1 and sys.argv[1] in ["full", "redeploy", "fix-webhook", "diagnose"]:
        agent_command(sys.argv[1])