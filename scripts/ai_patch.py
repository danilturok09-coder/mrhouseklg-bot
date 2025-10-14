# scripts/ai_patch.py
# ------------------------------------------------------------------------------
# Скрипт для генерации и применения патча (изменений в коде) через OpenAI API.
# Используется в Auto Dev (MrHouse). Принимает текстовое описание изменений
# и генерирует git-патч, который сразу применяется в репозитории.
# ------------------------------------------------------------------------------

import os
import subprocess
import sys
import tempfile
import pathlib
from textwrap import dedent
import requests

# === Модель OpenAI ============================================================
# gpt-4o — самая актуальная и стабильная модель API на 2025 год
MODEL = "gpt-4o"


# === Вспомогательные функции ==================================================
def run(cmd: str):
    """Выполняет shell-команду и выбрасывает ошибку при сбое."""
    subprocess.check_call(cmd, shell=True)


def git(*args):
    """Удобный вызов git-команд."""
    run("git " + " ".join(args))


# === Основная функция =========================================================
def main(prompt: str):
    """
    Основной сценарий:
    1. Проверяет наличие prompt (описание задачи).
    2. Создаёт новую ветку.
    3. Запрашивает у OpenAI diff-патч.
    4. Применяет изменения и делает коммит.
    """

    if not prompt.strip():
        print("⚠️  No prompt provided — skipping patch.")
        return

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    os.chdir(repo_root)

    branch = "autodev/" + str(abs(hash(prompt)))[:8]
    git("checkout -b", branch)

    # Собираем список файлов репозитория для контекста
    files = []
    for p in repo_root.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".txt", ".md", ".yaml", ".yml"):
            if ".git" in p.parts or "venv" in p.parts:
                continue
            files.append(str(p.relative_to(repo_root)))

    # === Подготавливаем запрос к OpenAI ======================================
    sys_prompt = dedent("""
    You are a professional software engineer.
    Your task: generate a unified diff patch (in git apply format)
    that applies requested changes to the repository.
    Return ONLY the patch, without explanations or extra text.
    Ensure valid syntax and indentation.
    """)

    user_content = (
        f"Change request:\n{prompt}\n\n"
        f"Repository files:\n" + "\n".join(files)
    )

    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    print(f"🤖 Sending prompt to OpenAI ({MODEL})...")
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        json=data,
        headers=headers,
        timeout=120,
    )

    if r.status_code != 200:
        print(f"❌ OpenAI API error: {r.status_code}\n{r.text}")
        sys.exit(1)

    patch = r.json()["choices"][0]["message"]["content"]
    print("✅ Patch received. Applying...")

    # === Применяем патч =======================================================
    with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
        tf.write(patch)
        tf.flush()
        try:
            run(f"git apply {tf.name}")
        except Exception as e:
            print("❌ Patch apply failed:", e)
            print("Patch content:\n", patch)
            sys.exit(1)

    git("add", "-A")
    git("commit", "-m", "'autodev: apply changes'")
    print("✅ Changes committed successfully!")


# === Запуск ==================================================================
if name == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="", help="Text of the change request")
    args = parser.parse_args()

    main(args.prompt)
