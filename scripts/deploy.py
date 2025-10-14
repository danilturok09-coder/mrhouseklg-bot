# scripts/deploy.py
# ------------------------------------------------------------------------------
# Запускает деплой на Render через Deploy Hook или API
# ------------------------------------------------------------------------------

import os
import requests
import sys

hook = os.environ.get("RENDER_DEPLOY_HOOK", "")
api = os.environ.get("RENDER_API_KEY", "")
sid = os.environ.get("RENDER_SERVICE_ID", "")

if hook:
    print("📤 Деплой через Deploy Hook...")
    r = requests.post(hook, timeout=20)
    print("Ответ Render:", r.status_code, r.text)
    sys.exit(0)

if api and sid:
    print("📤 Деплой через Render API...")
    r = requests.post(
        f"https://api.render.com/v1/services/{sid}/deploys",
        headers={"Authorization": f"Bearer {api}", "Accept": "application/json"},
        json={"clearCache": True},
        timeout=20,
    )
    print("Ответ Render:", r.status_code, r.text)
else:
    print("⚠️  Нет данных для деплоя — пропускаем.")
