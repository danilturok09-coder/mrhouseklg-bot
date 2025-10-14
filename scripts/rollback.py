# scripts/rollback.py
# ------------------------------------------------------------------------------
# Пробует «откатить» деплой на Render (по сути — запускает новый деплой
# предыдущего образа/версии). Работает через Render API.
# ------------------------------------------------------------------------------

import os
import requests

API = os.environ.get("RENDER_API_KEY", "")
SID = os.environ.get("RENDER_SERVICE_ID", "")

def main():
    if not (API and SID):
        print("⚠️  Нет RENDER_API_KEY или RENDER_SERVICE_ID — откат невозможен.")
        return

    r = requests.post(
        f"https://api.render.com/v1/services/{SID}/deploys",
        headers={"Authorization": f"Bearer {API}", "Accept": "application/json"},
        json={"clearCache": True},
        timeout=30,
    )
    print("↩️  Rollback (re-deploy) →", r.status_code, r.text)

if name == "__main__":
    main()
