# scripts/create_pr.py
# ------------------------------------------------------------------------------
# Создаёт Pull Request с изменениями, сгенерированными ai_patch.py
# ------------------------------------------------------------------------------

import os
import subprocess
import requests

def sh(cmd):
    """Возвращает результат shell-команды"""
    return subprocess.check_output(cmd, shell=True, text=True).strip()

def main():
    branch = sh("git rev-parse --abbrev-ref HEAD")
    if branch == "main":
        print("ℹ️  Ветка main — PR не нужен.")
        return

    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GH_TOKEN") or os.environ.get("MY_GITHUB_TOKEN")

    if not repo or not token:
        print("❌ Нет токена GH_TOKEN или MY_GITHUB_TOKEN")
        return

    print(f"📤 Создаю Pull Request из ветки {branch} → main")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "title": f"AutoDev: {branch}",
        "head": branch,
        "base": "main",
        "body": "Автоматический PR, сгенерированный AI-патчером 🤖",
    }
    r = requests.post(
        f"https://api.github.com/repos/{repo}/pulls",
        headers=headers,
        json=data,
        timeout=60,
    )
    print("✅ Результат:", r.status_code, r.text)

if name == "__main__":
    main()
