import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# === ENV ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")  # https://...onrender.com

# === Logs + диагностика версии PTB ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram, '__version__', 'unknown')} | module={telegram.__file__}")
except Exception:
    pass

# === Telegram Application (PTB v20) ===
application = Application.builder().token(BOT_TOKEN).build()
_initialized = False

def ensure_initialized():
    """Инициализировать PTB один раз (синхронно через asyncio.run)."""
    global _initialized
    if not _initialized:
        asyncio.run(application.initialize())
        _initialized = True
        logger.info("✅ Telegram Application initialized")

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

# Регистрация команд
application.add_handler(CommandHandler(["start", "star"], start))
application.add_handler(CommandHandler("ping", ping))
application.add_handler(MessageHandler(filters.Regex(r"^/?star$"), start))

# === Flask app (все роуты СИНХРОННЫЕ) ===
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.get("/set_webhook")
def set_webhook_route():
    if not BASE_URL:
        return "BASE_URL не задан", 400
    url = f"{BASE_URL}/webhook"
    try:
        # Ставим вебхук синхронно
        asyncio.run(application.bot.set_webhook(url, secret_token=WEBHOOK_SECRET))
        return f"Webhook установлен на {url}"
    except Exception as e:
        logger.exception("Ошибка при установке вебхука")
        return f"Ошибка при установке вебхука: {e}", 500

@web_app.post("/webhook")
def webhook():
    """Приём апдейтов от Telegram. Синхронный endpoint."""
    # 1) Проверка секрета
    header_secret = request.headers.get("X-Telegram-Bot-Secret-Token")
    if header_secret != WEBHOOK_SECRET:
        logger.warning("⛔️ Запрос с неверным секретом")
        return jsonify({"ok": False, "error": "forbidden"}), 403

    # 2) Разбор апдейта
    data = request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)

    # 3) Гарантируем единоразовую инициализацию PTB
    ensure_initialized()

    # 4) Обрабатываем апдейт синхронно
    try:
        asyncio.run(application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка обработки апдейта")
        return jsonify({"ok": False, "error": str(e)}), 500

# Локальный запуск
if __name__ == "__main__":
    if BASE_URL:
        url = f"{BASE_URL}/webhook"
        asyncio.run(application.bot.set_webhook(url, secret_token=WEBHOOK_SECRET))
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)