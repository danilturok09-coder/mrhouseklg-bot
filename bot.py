import os
import time
import logging
import asyncio
from urllib.parse import unquote
from flask import Flask, jsonify, request as flask_request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.request import HTTPXRequest

# ========= ENV =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")

# Принудительное обновление кэша Telegram
CACHE_VER = "2025-11-05-1"

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram,'__version__','unknown')} | module={telegram.__file__}")
except Exception:
    pass

# ========= GLOBAL LOOP =========
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)

# ========= PTB APP =========
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
    if _initialized:
        return
    LOOP.run_until_complete(application.initialize())
    _initialized = True
    logger.info("✅ Telegram Application initialized")

# ========= UI =========
MAIN_MENU = [
    ["📍 Локации домов", "🏗️ Проекты"],
    ["🧮 Расчёт стоимости", "🤖 Задать вопрос ИИ"],
    ["👨‍💼 Связаться с менеджером"]
]

def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ---- ЛОКАЦИИ ----
LOCATIONS = [
    "Шопино", "Чижовка", "Сивково",
    "Некрасово", "Груздово", "ВеснаЛэнд (Черносвитино)",
    "р-н магазина METRO", "г.Рязань", "Еловка", "КП Московский",
]

LOCATIONS_DATA = {
    "Шопино": {
        "photo": f"{BASE_URL}/static/locations/shopino/cover.jpg?v={CACHE_VER}" if BASE_URL else None,
        "caption": (
            "<b>Шопино</b>\n"
            "Посёлок с развитой инфраструктурой.\n"
            "В презентации: фото, видеообзор, планировки и описание."
        ),
        "presentation": f"{BASE_URL}/static/locations/shopino/presentation.pdf"
        if BASE_URL else "https://example.com/presentation-shopino.pdf",
    },
}

def make_locations_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ---- ПРОЕКТЫ ----
PROJECTS = ["Весна 90", "Весна 98", "Весна 105", "Весна 112"]

PROJECTS_DATA = {
    "Весна 90": {
        "photo": f"{BASE_URL}/static/projects/vesna90/vesna90.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 90</b>\n"
            "Чудесный дом 90 м² с большими окнами в пол, которые наполняют кухню-гостиную солнечным светом.\n\n"
            "• Кухня-гостиная: 24,4 м²\n"
            "• Спальня: 16,9 м²\n"
            "• Кабинет: 14,4 м²\n"
            "• Детская: 14,4 м²\n"
            "• Санузел: 5,9 м²\n"
            "• Прихожая: 12,2 м²\n"
            "• Крыльцо: 3,9 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna90/vesna90.pdf",
    },
    "Весна 98": {
        "photo": f"{BASE_URL}/static/projects/vesna98/vesna98.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 98</b>\n"
            "Удобный и комфортный проект 98 м² с потолком 4,5 м и панорамным остеклением в обеденной зоне.\n\n"
            "• Кухня-гостиная: 27,3 м²\n"
            "• Спальня: 17,1 м²\n"
            "• Детская: 14 м²\n"
            "• Кабинет: 14 м²\n"
            "• Санузел: 6 м²\n"
            "• Санузел гостевой: 2,5 м²\n"
            "• Прихожая: 13,3 м²\n"
            "• Крыльцо: 3,5 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna98/vesna98.pdf",
    },
    "Весна 105": {
        "photo": f"{BASE_URL}/static/projects/vesna105/vesna105.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 105</b>\n"
            "Увеличенная версия Весна-98 — ещё больше света и пространства.\n\n"
            "• Кухня-гостиная: 27,5 м²\n"
            "• Спальня: 18,6 м²\n"
            "• Детская: 16 м²\n"
            "• Кабинет: 16 м²\n"
            "• Санузел: 5,9 м²\n"
            "• Санузел гостевой: 2,7 м²\n"
            "• Прихожая: 14,1 м²\n"
            "• Крыльцо: 3,5 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna105/vesna105.pdf",
    },
    "Весна 112": {
        "photo": f"{BASE_URL}/static/projects/vesna112/vesna112.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 112</b>\n"
            "Те же большие окна в пол, что нравятся в Весна-90, плюс 3 спальни и 2 санузла.\n\n"
            "• Кухня-гостиная: 28,9 м²\n"
            "• Детская: 14,9 м²\n"
            "• Кабинет: 14,9 м²\n"
            "• Спальня: 19,2 м²\n"
            "• Санузел: 5,7 м²\n"
            "• Санузел 2: 1,6 м²\n"
            "• Гардероб: 6,7 м²\n"
            "• Прихожая: 15,2 м²\n"
            "• Крыльцо: 4,9 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna112/vesna112.pdf",
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
    """Приветствие + баннер + главное меню (антидубль 10с)."""
    now = time.time()
    last = context.user_data.get("_last_welcome_ts", 0)
    if now - last < 10:
        return
    context.user_data["_last_welcome_ts"] = now

    banner_url = f"{BASE_URL}/static/welcome.jpg" if BASE_URL else None
    caption = (
        "👋 Привет! Я бот <b>MR.House</b>.\n"
        "Помогу выбрать локацию и проект, посчитать стоимость и связать с менеджером."
    )

    chat_id = update.effective_chat.id
    sent_banner = False
    if banner_url:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=banner_url, caption=caption, parse_mode="HTML")
            sent_banner = True
        except Exception as e:
            logger.warning(f"Не смог отправить фото-баннер: {e}")

    if not sent_banner:
        await context.bot.send_message(chat_id=chat_id,
                                       text="👋 Привет! Я бот MR.House. Готов помочь.",
                                       parse_mode="HTML")
    await context.bot.send_message(chat_id=chat_id, text="Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

# ---- ЛОКАЦИИ ----
async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "LOC_LIST"
    text = "-----Вы в разделе локации домов-----\nВыберите локацию:"
    markup = make_locations_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

# ---- Исправленный send_location_card ----
async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = LOCATIONS_DATA.get(location_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{location_name}».")
        return

    photo_url = data.get("photo")
    presentation = data["presentation"]

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)],
        [InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])

    sent = False
    try:
        local_path = None
        if photo_url and BASE_URL and photo_url.startswith(f"{BASE_URL}/"):
            rel_url = photo_url[len(BASE_URL):].lstrip("/")
            rel_path = unquote(rel_url.split("?", 1)[0])
            if rel_path.startswith("static/"):
                local_path = rel_path

        if local_path and os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
            with open(local_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=InputFile(f, filename=os.path.basename(local_path)),
                    caption=data["caption"],
                    parse_mode="HTML",
                    reply_markup=markup
                )
                sent = True
    except Exception as e:
        logger.warning(f"send_photo(local) failed for {location_name}: {e}")

    if not sent and photo_url:
        try:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo_url,
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
            sent = True
        except Exception as e:
            logger.warning(f"send_photo(url) failed for {location_name}: {e}")

    if not sent:
        fallback_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Открыть изображение", url=photo_url or "")],
            [InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)],
            [InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])
        await context.bot.send_message(
            chat_id=chat.id,
            text=data["caption"],
            parse_mode="HTML",
            reply_markup=fallback_markup
        )