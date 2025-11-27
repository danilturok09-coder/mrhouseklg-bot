import os
import time
import logging
import asyncio
import re
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

# Куда слать заявки с расчёта
ADMIN_CHAT_ID = 759463205

# Принудительное обновление кэша Telegram (увидел новые картинки — увеличь версию)
CACHE_VER = "2025-11-05-3"

# ========= ЦЕНЫ / КОНФИГ ДЛЯ КАЛЬКУЛЯТОРА =========

# Стоимость коммуникаций (газ, свет, вода, канализация)
COMMUNICATIONS_PRICE = 500_000

# Чистовая отделка за м²
FINISH_PRICE_PER_M2 = 15_000

# Проекты для калькулятора: площадь и цена за тёплый контур
CALC_PROJECTS = {
    "Уют 90":      {"area": 90,  "shell_price": 5_200_000},
    "Весна 90":    {"area": 90,  "shell_price": 5_700_000},
    "Весна 98":    {"area": 98,  "shell_price": 6_000_000},
    "Весна 105":   {"area": 105, "shell_price": 6_200_000},
    "Простор 110": {"area": 110, "shell_price": 6_500_000},
    "Весна 112":   {"area": 112, "shell_price": 6_700_000},
    "Простор 114": {"area": 114, "shell_price": 6_700_000},
    "Простор 120": {"area": 120, "shell_price": 7_000_000},
    "Простор 130": {"area": 130, "shell_price": 7_900_000},
}

def format_rub(amount: int) -> str:
    """Форматируем цену: 5700000 -> '5 700 000 ₽'."""
    return f"{amount:,}".replace(",", " ") + " ₽"

def make_calc_projects_inline() -> InlineKeyboardMarkup:
    rows = []
    for name in CALC_PROJECTS.keys():
        rows.append([InlineKeyboardButton(name, callback_data=f"calc_proj:{name}")])
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

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

# ========= PTB APP (увеличенные таймауты) =========
tg_request = HTTPXRequest(
    connect_timeout=20.0,
    read_timeout=60.0,
    write_timeout=60.0,
    pool_timeout=20.0,
)
application = Application.builder().token(BOT_TOKEN).request(tg_request).build()
_initialized = False

def ensure_initialized() -> None:
    """Инициализируем PTB-Application ровно один раз в процессе."""
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

# ========= ЛОКАЦИИ (список, слаги, данные) =========
LOCATIONS = [
    "Шопино",
    "Чижовка",
    "р-н магазина METRO",
    "КП Южный",
    "Еловка",
    "ВеснаЛэнд (Черносвитино)",
    "Сивково",
    "Некрасово",
    "Груздово",
    "КП Московский",
]

# человекочитаемое название → slug (для путей к файлам)
LOC_SLUG = {
    "Шопино": "shopino",
    "Чижовка": "chizhovka",
    "р-н магазина METRO": "metro",
    "КП Южный": "kp_yuzhniy",
    "Еловка": "elovka",
    "ВеснаЛэнд (Черносвитино)": "vesnaland",
    "Сивково": "sivkovo",
    "Некрасово": "nekrasovo",
    "Груздово": "gruzdovo",
    "КП Московский": "kp_moskovskiy",
}

def _loc_data(name: str, body: str, *, has_video: bool=False) -> dict:
    slug = LOC_SLUG[name]
    photo = f"{BASE_URL}/static/locations/{slug}/{slug}.jpg?v={CACHE_VER}" if BASE_URL else None
    pres  = f"{BASE_URL}/static/locations/{slug}/{slug}.pdf" if BASE_URL else None
    video = f"{BASE_URL}/static/locations/{slug}/video.mp4" if (BASE_URL and has_video) else None
    caption = f"<b>{name}</b>\n{body}"
    return {"photo": photo, "presentation": pres, "video": video, "caption": caption}

# === ОПИСАНИЯ ЛОКАЦИЙ ===
LOCATIONS_DATA = {
    "Шопино": _loc_data(
        "Шопино",
        "Современный посёлок в шаге от города: школы и детские сады в 5–7 минутах, "
        "крупные ТЦ — около 10 минут на автомобиле. Спортивные площадки и прогулочные зоны рядом, "
        "а до центра города — примерно 15–20 минут. Очень развитая система общественного транспорта."
    ),
    "Чижовка": _loc_data(
        "Чижовка",
        "Локация с развитой инфраструктурой: детские учреждения и школы в пешей доступности в мкр. Веснушки, "
        "торговые точки и фитнес-клубы — 8–10 минут до ТЦ. До центра на машине — около 15–20 минут. "
        "Отличный выбор для активных родителей: спорт, учёба и комфорт рядом."
    ),
    "р-н магазина METRO": _loc_data(
        "р-н магазина METRO",
        "Район около крупного гипермаркета METRO: торговые и бытовые услуги — в шаговой доступности. "
        "Детские сады и школы — 5–10 минут, спортивные объекты — 10–12 минут. "
        "До центра города — около 15–20 минут. Удобен для семей и тех, кто ценит быстрый доступ к сервисам."
    ),
    "КП Южный": _loc_data(
        "КП Южный",
        "Современный посёлок окруженный лесом на 23 домовладения в шаге от города: школы и детские сады в 10–15 минутах, "
        "крупные ТЦ — около 10 минут на автомобиле, а до центра города — примерно 10–15 минут.",
        has_video=True  # хотим кнопку «Смотреть видео»
    ),
    "Еловка": _loc_data(
        "Еловка",
        "Спокойный посёлок для тех, кто хочет уединения, но оставаться в пределах города: "
        "школы и детсады есть, инфраструктура более пригородная. До центра — ~25–30 минут. "
        "Подойдёт для удалённой работы и более размеренного темпа жизни: рядом природа и меньше суеты."
    ),
    "ВеснаЛэнд (Черносвитино)": _loc_data(
        "ВеснаЛэнд (Черносвитино)",
        "Новая жилая зона с акцентом на семейный комфорт: дворовые площадки, зелёные зоны и удобные связи с городом. "
        "Детские учреждения и спорт — в близком окружении; до центра — около 10–15 минут. "
        "Одна из немногих локаций со всеми центральными коммуникациями."
    ),
    "Сивково": _loc_data(
        "Сивково",
        "Пригородная локация: дальше от центра (~30 минут), но плюсы — тишина, свежий воздух, больше пространства. "
        "Подходит тем, кто ценит размеренный стиль жизни, в том числе пенсионерам и удалённым специалистам."
    ),
    "Некрасово": _loc_data(
        "Некрасово",
        "Баланс близости и спокойствия: до центра — ~15–20 минут, школы и сады — 10–15 минут, "
        "торговля и спорт — чуть дальше. Комфорт загородной жизни без значительного удаления от города."
    ),
    "Груздово": _loc_data(
        "Груздово",
        "Спокойная локация с акцентом на проживание: до центра — ~30 минут, инфраструктура есть, "
        "но не ориентирована на интенсивный городской ритм. Хорошо для семей и тех, кто ценит тишину и пространство."
    ),
    "КП Московский": _loc_data(
        "КП Московский",
        "Коттеджный посёлок за городом: школы и сады — в пределах 10–15 минут на авто, до центра — ~20–25 минут. "
        "Подходит тем, кто хочет дом-«отдушину»: тишина, зелень, комфорт загородной жизни при гибком графике."
    ),
}

def make_locations_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= ПРОЕКТЫ (как были, для раздела «Проекты») =========
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

# ========= РАСЧЁТ СТОИМОСТИ =========

async def start_cost_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускаем калькулятор: выбор проекта."""
    context.user_data["state"] = "CALC_PROJECT"
    context.user_data["calc"] = {}

    chat_id = update.effective_chat.id
    if update.message:
        await update.message.reply_text(
            "-----Вы в разделе расчёт стоимости-----\n"
            "Сначала выберите проект дома:",
            reply_markup=ReplyKeyboardRemove()
        )
    await context.bot.send_message(
        chat_id=chat_id,
        text="Выберите проект:",
        reply_markup=make_calc_projects_inline()
    )

async def send_calc_result_and_ask_contact(query, context: ContextTypes.DEFAULT_TYPE, option_id: int):
    """Считаем стоимость и просим оставить контакты."""
    calc = context.user_data.get("calc") or {}
    project_name = calc.get("project")
    if not project_name or project_name not in CALC_PROJECTS:
        # Если вдруг потеряли состояние — вернём к выбору проекта
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Проект не выбран. Пожалуйста, начните расчёт заново.",
            reply_markup=make_calc_projects_inline()
        )
        context.user_data["state"] = "CALC_PROJECT"
        return

    info = CALC_PROJECTS[project_name]
    area = info["area"]
    shell_price = info["shell_price"]

    finish_cost = FINISH_PRICE_PER_M2 * area if option_id >= 2 else 0
    comm_cost = COMMUNICATIONS_PRICE if option_id >= 3 else 0
    total = shell_price + finish_cost + comm_cost

    if option_id == 1:
        variant = "Тёплый контур"
    elif option_id == 2:
        variant = "Тёплый контур + чистовая отделка"
    else:
        variant = "Тёплый контур + чистовая отделка + коммуникации"

    # Сохраняем в user_data, чтобы потом отправить админу
    context.user_data["calc"] = {
        "project": project_name,
        "area": area,
        "variant": variant,
        "shell_price": shell_price,
        "finish_cost": finish_cost,
        "comm_cost": comm_cost,
        "total": total,
    }

    lines = [
        "<b>Предварительный расчёт стоимости</b>",
        "",
        f"Проект: <b>{project_name}</b>",
        f"Площадь: {area} м²",
        "",
        f"Тёплый контур: {format_rub(shell_price)}",
    ]
    if finish_cost:
        lines.append(f"Чистовая отделка (15 000 ₽/м²): {format_rub(finish_cost)}")
    if comm_cost:
        lines.append(f"Коммуникации (газ, свет, вода, канализация): {format_rub(comm_cost)}")
    lines.append("")
    lines.append(f"<b>Итого ориентировочно: {format_rub(total)}</b>")
    lines.append("")
    lines.append("Расчёт предварительный и не учитывает стоимость участка.")
    lines.append("Если хотите получить точное коммерческое предложение — оставьте, пожалуйста, свои контакты.")

    text = "\n".join(lines)

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Оставить контакты менеджеру", callback_data="calc_leave_contact")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_menu")],
    ])

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=markup
    )

    context.user_data["state"] = "CALC_SUMMARY"

# ========= ЛОКАЦИИ (UI) =========
async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "LOC_LIST"
    text = "-----Вы в разделе локации домов-----\nВыберите локацию:"
    markup = make_locations_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

# Локация: сначала локальный файл → затем URL → затем fallback
async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = LOCATIONS_DATA.get(location_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{location_name}».")
        return

    photo_url = data.get("photo")
    presentation = data.get("presentation")
    video = data.get("video")

    # Кнопки без дублей: сначала презентация, потом видео
    buttons = []
    if presentation:
        buttons.append([InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)])
    if video:
        buttons.append([InlineKeyboardButton("🎬 Смотреть видео", url=video)])
    buttons.append([InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")])
    buttons.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    markup = InlineKeyboardMarkup(buttons)

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
        # Последний резерв: только текст + кнопки
        await context.bot.send_message(
            chat_id=chat.id,
            text=data["caption"],
            parse_mode="HTML",
            reply_markup=markup
        )

# ========= ПРОЕКТЫ (UI) =========
async def show_projects_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "PROJ_LIST"
    text = "-----Вы в разделе проекты-----\nВыберите проект:"
    markup = make_projects_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Проекты:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

# Проект: локальный файл → URL → fallback
async def send_project_card(chat, project_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = PROJECTS_DATA.get(project_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{project_name}».")
        return

    photo_url = data.get("photo")
    presentation = data["presentation"]

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)],
        [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
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
        logger.warning(f"send_photo(local) failed for {project_name}: {e}")

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
            logger.warning(f"send_photo(url) failed for {project_name}: {e}")

    if not sent:
        await context.bot.send_message(
            chat_id=chat.id,
            text=data["caption"],
            parse_mode="HTML",
            reply_markup=markup
        )

# ========= COMMANDS & ROUTING =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_welcome_with_photo(update, context)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "MAIN"
    await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Бот работает ✅")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state", "MAIN")

    # Эти кнопки должны срабатывать из любого состояния
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if text == "🧮 Расчёт стоимости":
        return await start_cost_calculation(update, context)

    if text == "👨‍💼 Связаться с менеджером":
        # Простое сообщение + главное меню
        return await update.message.reply_text(
            "Наш менеджер свяжется с вами: +7 (910) 864-07-37",
            reply_markup=kb(MAIN_MENU)
        )

    # Приём контакта после расчёта
    if state == "CALC_WAIT_CONTACT":
        calc = context.user_data.get("calc") or {}
        user = update.effective_user
        chat_id = update.effective_chat.id

        admin_text_lines = [
            "🆕 Новая заявка с расчёта стоимости",
            "",
            f"Пользователь: {user.full_name} (id: {user.id})",
        ]
        if user.username:
            admin_text_lines.append(f"username: @{user.username}")
        admin_text_lines.append(f"Чат id: {chat_id}")
        admin_text_lines.append("")
        admin_text_lines.append("Контакты от пользователя:")
        admin_text_lines.append(text)
        admin_text_lines.append("")

        if calc:
            admin_text_lines.append("Расчёт:")
            admin_text_lines.append(f"Проект: {calc.get('project')}")
            admin_text_lines.append(f"Площадь: {calc.get('area')} м²")
            admin_text_lines.append(f"Вариант: {calc.get('variant')}")
            admin_text_lines.append(f"Тёплый контур: {format_rub(calc.get('shell_price', 0))}")
            if calc.get("finish_cost"):
                admin_text_lines.append(f"Чистовая: {format_rub(calc.get('finish_cost', 0))}")
            if calc.get("comm_cost"):
                admin_text_lines.append(f"Коммуникации: {format_rub(calc.get('comm_cost', 0))}")
            admin_text_lines.append(f"Итого: {format_rub(calc.get('total', 0))}")

        admin_text = "\n".join(admin_text_lines)

        # Отправляем тебе в личку
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_text
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить заявку админу: {e}")

        # Ответ пользователю
        await update.message.reply_text(
            "Спасибо! Я передал ваш запрос менеджеру. "
            "Он свяжется с вами в ближайшее время.",
            reply_markup=kb(MAIN_MENU)
        )
        context.user_data["state"] = "MAIN"
        context.user_data["calc"] = {}
        return

    # Базовая логика главного меню
    if state == "MAIN":
        return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

    return  # остальное — кликами по inline

async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()

    # ====== КАЛЬКУЛЯТОР КОЛБЭКИ ======
    if data.startswith("calc_proj:"):
        project_name = data.split(":", 1)[1]
        context.user_data["state"] = "CALC_PROJECT"
        context.user_data["calc"] = {"project": project_name}

        text = (
            f"Проект: <b>{project_name}</b>\n"
            "Что рассчитать?"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Тёплый контур", callback_data="calc_opt:1")],
            [InlineKeyboardButton("Тёплый контур + чистовая отделка", callback_data="calc_opt:2")],
            [InlineKeyboardButton("Тёплый контур + чистовая + коммуникации", callback_data="calc_opt:3")],
            [InlineKeyboardButton("🔙 Выбрать другой проект", callback_data="calc_back_projects")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_menu")],
        ])
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup
            )
        return

    if data == "calc_back_projects":
        context.user_data["state"] = "CALC_PROJECT"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите проект:",
            reply_markup=make_calc_projects_inline()
        )
        return

    if data.startswith("calc_opt:"):
        try:
            option_id = int(data.split(":", 1)[1])
        except ValueError:
            option_id = 1
        await send_calc_result_and_ask_contact(query, context, option_id)
        return

    if data == "calc_leave_contact":
        context.user_data["state"] = "CALC_WAIT_CONTACT"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Напишите, пожалуйста, как к вам обращаться и номер телефона одним сообщением.\n\n"
                 "Например: «Алексей, +7 999 123-45-67»"
        )
        return

    # ====== ЛОКАЦИИ ======
    if data.startswith("loc:"):
        loc = data[4:]
        try:
            await query.edit_message_text(f"Локация {loc}:")
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await send_location_card(query.message.chat, loc, context)

    if data == "back_to_locs":
        try:
            await query.edit_message_text("Выберите локацию:")
            await query.edit_message_reply_markup(reply_markup=make_locations_inline())
        except Exception:
            await context.bot.send_message(query.message.chat_id, "Выберите локацию:", reply_markup=make_locations_inline())
        context.user_data["state"] = "LOC_LIST"
        return

    # ====== ПРОЕКТЫ ======
    if data.startswith("proj:"):
        proj = data[5:]
        try:
            await query.edit_message_text(f"Проект {proj}:")
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await send_project_card(query.message.chat, proj, context)

    if data == "back_to_projects":
        try:
            await query.edit_message_text("Выберите проект:")
            await query.edit_message_reply_markup(reply_markup=make_projects_inline())
        except Exception:
            await context.bot.send_message(query.message.chat_id, "Выберите проект:", reply_markup=make_projects_inline())
        context.user_data["state"] = "PROJ_LIST"
        return

    # ====== В МЕНЮ ======
    if data == "back_to_menu":
        context.user_data.clear()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await send_welcome_with_photo(query_update, context)

# Регистрация
application.add_handler(CommandHandler(["start", "star"], cmd_start))
application.add_handler(CommandHandler("menu", cmd_menu))
application.add_handler(CommandHandler("ping", cmd_ping))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(error_handler)

# ========= FLASK (экспортируем 'web_app') =========
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.get("/set_webhook")
def set_webhook_route():
    if not BASE_URL:
        return "BASE_URL не задан", 400
    ensure_initialized()
    url = f"{BASE_URL}/webhook"
    try:
        LOOP.run_until_complete(application.bot.set_webhook(url))
        return f"Webhook установлен на {url}"
    except Exception as e:
        logger.exception("Ошибка при установке вебхука")
        return f"Ошибка при установке вебхука: {e}", 500

@web_app.post("/webhook")
def webhook():
    ensure_initialized()
    data = flask_request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)
    try:
        LOOP.run_until_complete(application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка обработки апдейта")
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    if BASE_URL:
        ensure_initialized()
        LOOP.run_until_complete(application.bot.set_webhook(f"{BASE_URL}/webhook"))
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)