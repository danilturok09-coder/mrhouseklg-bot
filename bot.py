import os
import logging
import asyncio
from flask import Flask, request, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# === Конфиг из окружения (Render/GitHub Secrets) ===
BOT_TOKEN = os.environ["BOT_TOKEN"]                 # токен из @BotFather
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]       # твой секрет для вебхука
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")  # https://<service>.onrender.com

# === Логи ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Telegram Application (PTB v20, async) ===
application = Application.builder().token(BOT_TOKEN).build()

# Фикс «/start отвечает со второй попытки» — инициализируем один раз
_initialized = False
_init_lock = asyncio.Lock()

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Узнать стоимость строительства", callback_data="price"),
            InlineKeyboardButton("Наши проекты", callback_data="projects"),
        ],
        [
            InlineKeyboardButton("Контакты", callback_data="contacts"),
            InlineKeyboardButton("О компании", callback_data="about"),
        ],
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот MR.House. Чем могу помочь?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Бот работает ✅")

# Регистрация команд и «частой опечатки» /star
application.add_handler(CommandHandler(["start", "star"], start))
application.add_handler(CommandHandler("ping", ping))
application.add_handler(MessageHandler(filters.Regex(r"^/?star$"), start))

# === Flask (WSGI) приложение ===
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.get("/set_webhook")
def set_webhook_route():
    """Ручная установка вебхука (обычно не нужна — делает ops-агент)."""
    if not BASE_URL:
        return "BASE_URL не задан", 400
    url = f"{BASE_URL}/webhook"
    try:
        asyncio.get_event_loop().run_until_complete(
            application.bot.set_webhook(url, secret_token=WEBHOOK_SECRET)
        )
        return f"Webhook установлен на {url}"
    except Exception as e:
        logger.exception("Ошибка при установке вебхука")
        return f"Ошибка при установке вебхука: {e}", 500

@web_app.post("/webhook")
async def webhook():
    """Приём апдейтов от Telegram с проверкой секрета."""
    # 1) Проверка секрета
    header_secret = request.headers.get("X-Telegram-Bot-Secret-Token")
    if header_secret != WEBHOOK_SECRET:
        logger.warning("⛔️ Запрос с неверным секретом")
        return jsonify({"ok": False, "error": "forbidden"}), 403

    # 2) Разбор update
    data = request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)

    # 3) Единоразовая инициализация PTB
    global _initialized
    if not _initialized:
        async with _init_lock:
            if not _initialized:
                await application.initialize()
                _initialized = True
                logger.info("✅ Telegram Application initialized")

    # 4) Обработка
    try:
        await application.process_update(update)
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка обработки апдейта")
        return jsonify({"ok": False, "error": str(e)}), 500


# Локальный запуск (на Render не используется)
if __name__ == "__main__":
    if BASE_URL:
        url = f"{BASE_URL}/webhook"
        asyncio.get_event_loop().run_until_complete(
            application.bot.set_webhook(url, secret_token=WEBHOOK_SECRET)
        )
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)