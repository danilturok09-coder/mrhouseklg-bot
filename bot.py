import os
import time
import logging
import asyncio
from flask import Flask, jsonify, request as flask_request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.request import HTTPXRequest

# ========= ENV =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ========= GLOBAL LOOP =========
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)

# ========= PTB APP (увеличены таймауты) =========
tg_request = HTTPXRequest(
    connect_timeout=20.0,
    read_timeout=60.0,
    write_timeout=60.0,
    pool_timeout=20.0,
)
application = Application.builder().token(BOT_TOKEN).request(tg_request).build()
_initialized = False

def ensure_initialized() -> None:
    global _initialized
    if not _initialized:
        LOOP.run_until_complete(application.initialize())
        _initialized = True
        logger.info("✅ Telegram Application initialized")

# ---------- утилита кеш-бастера ----------
def versioned(url: str) -> str:
    """Добавляем ?v=<timestamp> (или &v=...), чтобы обойти кеш Telegram."""
    if not url:
        return url
    ts = int(time.time())
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={ts}"

# ========= UI =========
MAIN_MENU = [
    ["📍 Локации домов", "🏗️ Проекты"],
    ["🧮 Расчёт стоимости", "🤖 Задать вопрос ИИ"],
    ["👨‍💼 Связаться с менеджером"]
]

def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ========= ЛОКАЦИИ =========
LOCATIONS = [
    "Шопино", "Чижовка", "Сивково",
    "Некрасово", "Груздово", "ВеснаЛэнд (Черносвитино)",
    "р-н магазина METRO", "г.Рязань", "Еловка", "КП Московский",
]

# Храним базовые пути без версий:
LOCATIONS_DATA = {
    "Шопино": {
        "photo_path": f"{BASE_URL}/static/locations/shopino/cover.jpg" if BASE_URL else None,
        "presentation_path": f"{BASE_URL}/static/locations/shopino/presentation.pdf" if BASE_URL else None,
        "caption": (
            "<b>Шопино</b>\n"
            "Посёлок с развитой инфраструктурой. Удобное расположение, дороги, коммуникации.\n"
            "В презентации: фото, видеообзор, планировки и описание."
        ),
    },
    # добавляй остальные по образцу
}

def make_locations_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= ПРОЕКТЫ =========
PROJECTS = ["Весна 90", "Весна 98", "Весна 105", "Весна 112"]

PROJECTS_DATA = {
    "Весна 90": {
        "photo_path": f"{BASE_URL}/static/projects/vesna90/vesna90.jpg" if BASE_URL else None,
        "presentation_path": f"{BASE_URL}/static/projects/vesna90/vesna90.pdf" if BASE_URL else None,
        "caption": (
            "<b>Весна 90</b>\n"
            "Уютный одноэтажный дом с большими окнами и просторной кухней-гостиной.\n"
            "Идеален для семьи из 3–4 человек."
        ),
    },
    "Весна 98": {
        "photo_path": f"{BASE_URL}/static/projects/vesna98/vesna98.jpg" if BASE_URL else None,
        "presentation_path": f"{BASE_URL}/static/projects/vesna98/vesna98.pdf" if BASE_URL else None,
        "caption": (
            "<b>Весна 98</b>\n"
            "Комфортный проект с панорамными окнами и высоким потолком до 4,5 м."
        ),
    },
    "Весна 105": {
        "photo_path": f"{BASE_URL}/static/projects/vesna105/vesna105.jpg" if BASE_URL else None,
        "presentation_path": f"{BASE_URL}/static/projects/vesna105/vesna105.pdf" if BASE_URL else None,
        "caption": (
            "<b>Весна 105</b>\n"
            "Современный дом с увеличенной площадью и просторными спальнями."
        ),
    },
    "Весна 112": {
        "photo_path": f"{BASE_URL}/static/projects/vesna112/vesna112.jpg" if BASE_URL else None,
        "presentation_path": f"{BASE_URL}/static/projects/vesna112/vesna112.pdf" if BASE_URL else None,
        "caption": (
            "<b>Весна 112</b>\n"
            "Современный проект с тремя спальнями и двумя санузлами."
        ),
    },
}

def make_projects_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"🏡 {name}", callback_data=f"proj:{name}")] for name in PROJECTS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= HELPERS =========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("❗ Unhandled error", exc_info=context.error)

async def send_welcome_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last = context.user_data.get("_last_welcome_ts", 0)
    if now - last < 10:
        return
    context.user_data["_last_welcome_ts"] = now

    banner_path = f"{BASE_URL}/static/welcome.jpg" if BASE_URL else None
    banner_url = versioned(banner_path) if banner_path else None

    caption = (
        "👋 Привет! Я бот <b>MR.House</b>.\n"
        "Помогу выбрать локацию, проект и связаться с менеджером."
    )

    chat_id = update.effective_chat.id
    try:
        if banner_url:
            await context.bot.send_photo(chat_id=chat_id, photo=banner_url, caption=caption, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не смог отправить баннер: {e}")

    await context.bot.send_message(chat_id=chat_id, text="Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

# ========= ЛОКАЦИИ =========
async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "LOC_LIST"
    text = "----- Раздел: Локации домов -----\nВыберите локацию:"
    markup = make_locations_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

async def send_location_card(chat, loc_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = LOCATIONS_DATA.get(loc_name)
    if not data:
        await context.bot.send_message(chat.id, f"Скоро добавим карточку для «{loc_name}».")
        return

    photo_url = versioned(data.get("photo_path") or "")
    pres_url  = versioned(data.get("presentation_path") or "")

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=pres_url)],
        [InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])
    try:
        await context.bot.send_photo(chat.id, photo=photo_url, caption=data["caption"], parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.warning(f"Ошибка отправки фото: {e}")
        await context.bot.send_message(chat.id, text=data["caption"], parse_mode="HTML", reply_markup=markup)

# ========= ПРОЕКТЫ =========
async def show_projects_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "PROJ_LIST"
    markup = make_projects_inline()
    text = "----- Раздел: Проекты домов -----\nВыберите проект:"
    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Проекты:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

async def send_project_card(chat, proj_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = PROJECTS_DATA.get(proj_name)
    if not data:
        await context.bot.send_message(chat.id, f"Скоро добавим карточку для «{proj_name}».")
        return

    photo_url = versioned(data.get("photo_path") or "")
    pres_url  = versioned(data.get("presentation_path") or "")

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=pres_url)],
        [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])
    try:
        await context.bot.send_photo(chat.id, photo=photo_url, caption=data["caption"], parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.warning(f"Ошибка отправки фото проекта: {e}")
        # Фоллбек с кнопкой "Открыть изображение"
        fallback = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Открыть изображение", url=photo_url)],
            [InlineKeyboardButton("📘 Смотреть презентацию", url=pres_url)],
            [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])
        await context.bot.send_message(chat.id, text=data["caption"], parse_mode="HTML", reply_markup=fallback)

# ========= COMMANDS =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_welcome_with_photo(update, context)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Бот работает ✅")

# ========= CALLBACKS =========
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)
    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)
    mapping = {
        "🧮 Расчёт стоимости": "Введите желаемую площадь и бюджет (пока заглушка).",
        "🤖 Задать вопрос ИИ": "Напишите вопрос, я постараюсь помочь (пока заглушка).",
        "👨‍💼 Связаться с менеджером": "Наш менеджер свяжется с вами: +7 (910) 864-07-37",
    }
    if text in mapping:
        return await update.message.reply_text(mapping[text], reply_markup=kb(MAIN_MENU))
    return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()

    if data.startswith("loc:"):
        loc = data[4:]
        return await send_location_card(query.message.chat, loc, context)

    if data == "back_to_locs":
        return await query.message.edit_text("Выберите локацию:", reply_markup=make_locations_inline())

    if data.startswith("proj:"):
        proj = data[5:]
        return await send_project_card(query.message.chat, proj, context)

    if data == "back_to_projects":
        return await query.message.edit_text("Выберите проект:", reply_markup=make_projects_inline())

    if data == "back_to_menu":
        return await send_welcome_with_photo(query_update, context)

# ========= REGISTRATION =========
application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(CommandHandler("menu", cmd_menu))
application.add_handler(CommandHandler("ping", cmd_ping))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_error_handler(error_handler)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ========= FLASK =========
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.post("/webhook")
def webhook():
    ensure_initialized()
    data = flask_request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)
    LOOP.run_until_complete(application.process_update(update))
    return jsonify({"ok": True})

if __name__ == "__main__":
    if BASE_URL:
        ensure_initialized()
        LOOP.run_until_complete(application.bot.set_webhook(f"{BASE_URL}/webhook"))
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)