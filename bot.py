# bot.py
import os
import logging
import asyncio
from typing import Dict, Any

from flask import Flask, request, url_for

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ==== Конфигурация через переменные окружения ====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BASE_URL = os.environ.get("BASE_URL", "").strip()  # https://mrhouseklg-bot.onrender.com
MANAGER_USERNAME = os.environ.get("MANAGER_USERNAME", "")  # опционально @username
MANAGER_PHONE = os.environ.get("MANAGER_PHONE", "")        # опционально +7...

if not BOT_TOKEN or not BASE_URL:
    raise RuntimeError("Нужны переменные окружения BOT_TOKEN и BASE_URL")

# ==== Логи ====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ==== Flask ====
web_app = Flask(__name__, static_folder="static", static_url_path="/static")

# ==== Telegram application ====
application = Application.builder().token(BOT_TOKEN).build()

# ----------------------------------------------------------------------
# ДАННЫЕ
# ----------------------------------------------------------------------

# Локации (inline-список)
LOCATIONS = [
    "Шопино",
    "Чижовка",
    "Сивково",
    "Некрасово",
    "Груздово",
    "ВеснаЛэнд (Черноcвитино)",
    "р-н магазина МЕТРО",
    "г. Рязань",
    "Еловка",
    "КП Московский",
]

# Проекты (любой cover/presentation — указывайте реальные имена файлов)
# Файлы кладём в: static/projects/<slug>/
PROJECTS: Dict[str, Dict[str, Any]] = {
    "vesna90": {
        "title": "Весна 90",
        "desc": "Компактный и светлый проект на 90 м² — идеален как первый дом.",
        "cover": "vesna90.jpg",         # например: static/projects/vesna90/vesna90.jpg
        "presentation": "vesna90.pdf",  # например: static/projects/vesna90/vesna90.pdf
    },
    "vesna98": {
        "title": "Весна 98",
        "desc": "Удобная планировка и панорамное остекление в столовой зоне.",
        "cover": "vesna98.jpg",
        "presentation": "vesna98.pdf",
    },
    "vesna105": {
        "title": "Весна 105",
        "desc": "Увеличенная версия 98-го — больше пространства и света.",
        "cover": "vesna105.jpg",
        "presentation": "vesna105.pdf",
    },
    "vesna112": {
        "title": "Весна 112",
        "desc": "Солнечная кухня-гостиная, две ванные, коридор с хранением.",
        "cover": "vesna112.jpg",
        "presentation": "vesna112.pdf",
    },
}

WELCOME_IMAGE_PATH = "static/welcome.jpg"  # локальный путь в репо

# ----------------------------------------------------------------------
# УТИЛИТЫ КЛАВИАТУР
# ----------------------------------------------------------------------

def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📍 Локации домов", callback_data="menu:locations")],
        [InlineKeyboardButton("📐 Наши проекты", callback_data="menu:projects")],
        [
            InlineKeyboardButton("🧮 Расчёт стоимости", callback_data="menu:calc"),
            InlineKeyboardButton("🤖 Вопрос ИИ", callback_data="menu:ai"),
        ],
        [InlineKeyboardButton("👤 Менеджер", callback_data="menu:manager")],
    ]
    return InlineKeyboardMarkup(rows)

def locations_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(title, callback_data=f"loc:{title}") ] for title in LOCATIONS]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:main")])
    return InlineKeyboardMarkup(rows)

def projects_kb() -> InlineKeyboardMarkup:
    rows = []
    for slug, meta in PROJECTS.items():
        rows.append([InlineKeyboardButton(meta["title"], callback_data=f"proj:{slug}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:main")])
    return InlineKeyboardMarkup(rows)

def back_to_locations_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ К локациям", callback_data="menu:locations")],
         [InlineKeyboardButton("🏠 В главное меню", callback_data="back:main")]]
    )

def back_to_projects_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ К проектам", callback_data="menu:projects")],
         [InlineKeyboardButton("🏠 В главное меню", callback_data="back:main")]]
    )

# ----------------------------------------------------------------------
# ХЕНДЛЕРЫ КОМАНД
# ----------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat

    # Приветственная картинка (молча пропускаем, если файла нет)
    if os.path.exists(WELCOME_IMAGE_PATH):
        try:
            with open(WELCOME_IMAGE_PATH, "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=f,
                    caption=(
                        "👋 Привет! Я бот **MR.House**.\n"
                        "Помогу выбрать локацию и проект, посчитать стоимость "
                        "и связать с менеджером."
                    ),
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.warning("Не удалось отправить welcome.jpg: %s", e)

    # Текст + меню
    await update.message.reply_text(
        "Выберите раздел 👇",
        reply_markup=main_menu_kb(),
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")

# ----------------------------------------------------------------------
# ХЕНДЛЕРЫ CALLBACK (INLINE-КНОПКИ)
# ----------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    chat_id = query.message.chat_id

    # Главное меню
    if data == "back:main":
        await query.edit_message_text("Выберите раздел 👇", reply_markup=main_menu_kb())
        return

    # Меню: Локации
    if data == "menu:locations":
        await query.edit_message_text("-----Вы в разделе локации домов-----\nВыберите локацию:",
                                      reply_markup=locations_kb())
        return

    # Меню: Проекты
    if data == "menu:projects":
        await query.edit_message_text("-----Вы в разделе проекты-----\nВыберите проект:",
                                      reply_markup=projects_kb())
        return

    # Кнопка менеджера
    if data == "menu:manager":
        text = "Связаться с менеджером:\n"
        if MANAGER_USERNAME:
            text += f"• Telegram: {MANAGER_USERNAME}\n"
        if MANAGER_PHONE:
            text += f"• Телефон: {MANAGER_PHONE}"
        if not (MANAGER_USERNAME or MANAGER_PHONE):
            text += "Контакты будут добавлены позже."
        await query.edit_message_text(text, reply_markup=back_to_main_or_menu())
        return

    # Заглушки (расчёт/ИИ)
    if data == "menu:calc":
        await query.edit_message_text(
            "🧮 Калькулятор стоимости скоро подключим. "
            "Напишите, какие параметры важны: площадь, материал, участок и т.д.",
            reply_markup=back_to_main_or_menu(),
        )
        return

    if data == "menu:ai":
        await query.edit_message_text(
            "🤖 Задайте вопрос текстом, я отвечу. (Раздел в разработке)",
            reply_markup=back_to_main_or_menu(),
        )
        return

    # Выбор локации
    if data.startswith("loc:"):
        title = data.split("loc:", 1)[1]
        caption = f"Локация **{title}**.\nОпишите, что показать: остатки, план, коммуникации?"
        await query.edit_message_caption(
            caption,
            parse_mode="Markdown"
        ) if query.message.photo else await query.edit_message_text(
            caption, parse_mode="Markdown", reply_markup=back_to_locations_kb()
        )
        # Если было не фото, добавим кнопки:
        if not query.message.photo:
            await query.edit_message_text(
                caption,
                parse_mode="Markdown",
                reply_markup=back_to_locations_kb(),
            )
        return

    # Выбор проекта
    if data.startswith("proj:"):
        slug = data.split("proj:", 1)[1]
        meta = PROJECTS.get(slug)
        if not meta:
            await query.edit_message_text("Проект не найден.", reply_markup=projects_kb())
            return

        # Готовим ссылки на обложку и презентацию
        cover_url = f"{BASE_URL}/static/projects/{slug}/{meta['cover']}"
        pres_url = f"{BASE_URL}/static/projects/{slug}/{meta['presentation']}"
        caption = f"*{meta['title']}*\n{meta.get('desc','')}\n\n📄 Презентация: {pres_url}"

        # Если предыдущее сообщение было с фото — заменим его через media
        try:
            if query.message.photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=cover_url, caption=caption, parse_mode="Markdown"),
                    reply_markup=back_to_projects_kb(),
                )
            else:
                # Иначе отправим новое фото и отредактируем предыдущее «текстом»
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=cover_url,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=back_to_projects_kb(),
                )
                await query.edit_message_text(
                    f"Вы выбрали проект: {meta['title']}",
                    reply_markup=back_to_projects_kb(),
                )
        except Exception as e:
            logger.warning("Не удалось отправить медиа проекта %s: %s", slug, e)
            await query.edit_message_text(
                f"{meta['title']}\n{meta.get('desc','')}\n\n📄 Презентация: {pres_url}",
                reply_markup=back_to_projects_kb(),
            )
        return


def back_to_main_or_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 В главное меню", callback_data="back:main")]]
    )

# ----------------------------------------------------------------------
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ----------------------------------------------------------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("ping", ping))
application.add_handler(CallbackQueryHandler(on_callback))

# ----------------------------------------------------------------------
# FLASK РОУТЫ (WEBHOOK)
# ----------------------------------------------------------------------

@web_app.get("/")
def index():
    return "MR.House bot is up."

@web_app.get("/set_webhook")
def set_webhook():
    """Ручная установка вебхука (GET в браузере)."""
    url = f"{BASE_URL}/webhook"
    try:
        asyncio.run(application.bot.set_webhook(url))
        return f"Webhook установлен на {url}"
    except Exception as e:
        logger.exception("Ошибка set_webhook")
        return f"Ошибка при установке вебхука: {e}", 500

@web_app.post("/webhook")
def receive_webhook():
    """Сюда Telegram шлёт апдейты. Flask синхронный — внутри запускаем asyncio.run"""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.initialize())
        asyncio.run(application.process_update(update))
        return "OK"
    except Exception as e:
        logger.exception("Ошибка обработки апдейта")
        return f"Error: {e}", 500

# Локальный запуск (не используется на Render, но удобно для отладки)
if __name__ == "__main__":
    # Установка вебхука при локальном старте (опционально)
    try:
        asyncio.run(application.bot.set_webhook(f"{BASE_URL}/webhook"))
    except Exception as e:
        logger.warning("set_webhook при локальном старте: %s", e)

    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
    