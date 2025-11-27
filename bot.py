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

# Принудительное обновление кэша Telegram (увидел новые картинки — увеличь версию)
CACHE_VER = "2025-11-05-3"

# Куда слать заявки с расчётов
ADMIN_CHAT_ID = 759463205

# ========= ЛОГИ =========
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

# ========= ЦЕНЫ ДЛЯ КАЛЬКУЛЯТОРА =========

# Проекты и их цена за тёплый контур (из твоего сообщения)
PROJECT_PRICES = {
    "Уют 90": 5_200_000,
    "Весна 90": 5_700_000,
    "Весна 98": 6_000_000,
    "Весна 105": 6_200_000,
    "Простор 110": 6_500_000,
    "Весна 112": 6_700_000,
    "Простор 114": 6_700_000,
    "Простор 120": 7_000_000,
    "Простор 130": 7_900_000,
}

# Порядок отображения в калькуляторе
PROJECT_CHOICES = [
    "Уют 90",
    "Весна 90",
    "Весна 98",
    "Весна 105",
    "Простор 110",
    "Весна 112",
    "Простор 114",
    "Простор 120",
    "Простор 130",
]

# Стоимость м² для индивидуальной площади
PRICE_WARM_1F = 63_300   # одноэтажный
PRICE_WARM_2F = 61_300   # двухэтажный
PRICE_PREDCHIST = 15_000 # предчистовая отделка, за м²
PRICE_COMM = 500_000     # коммуникации, фикс

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

# ========= ПРОЕКТЫ (как были для карточек) =========
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
        await context.bot.send_message(
            chat_id=chat_id,
            text="👋 Привет! Я бот MR.House. Готов помочь.",
            parse_mode="HTML"
        )
    await context.bot.send_message(chat_id=chat_id, text="Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

# ========= КАЛЬКУЛЯТОР: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =========

def parse_area_from_name(name: str) -> int | None:
    """Достаём число из названия проекта (Уют 90 → 90)."""
    m = re.search(r"(\d+)", name)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

def format_money(x: int) -> str:
    return f"{x:,}".replace(",", " ")

def build_calc_text(calc: dict) -> str:
    """Собираем красивый текст расчёта."""
    mode = calc.get("mode")
    area = calc.get("area")
    floors = calc.get("floors")
    include_pred = calc.get("include_pred", False)
    include_comm = calc.get("include_comm", False)
    warm_price = calc.get("warm_price", 0)
    pred_price = calc.get("pred_price", 0)
    comm_price = calc.get("comm_price", 0)
    total = calc.get("total", 0)

    lines = []
    lines.append("🧮 <b>Предварительный расчёт</b>\n")

    if mode == "standard":
        proj = calc.get("project_name")
        lines.append(f"🏡 Проект: <b>{proj}</b>")
        if area:
            lines.append(f"Площадь: ~{area} м²")
    else:
        lines.append("📐 Индивидуальная площадь")
        if area:
            lines.append(f"Площадь: <b>{area} м²</b>")
        if floors:
            if floors == 1:
                lines.append("Этажность: <b>1 этаж</b>")
            else:
                lines.append("Этажность: <b>2 этажа</b>")

    lines.append("")  # пустая строка

    lines.append(f"🔥 Тёплый контур: <b>{format_money(warm_price)} ₽</b>")

    if include_pred:
        lines.append(f"🎨 Предчистовая отделка: <b>{format_money(pred_price)} ₽</b>")
    else:
        lines.append("🎨 Предчистовая отделка: не включена")

    if include_comm:
        lines.append(f"🔌 Коммуникации (газ, свет, вода, канализация): <b>{format_money(comm_price)} ₽</b>")
    else:
        lines.append("🔌 Коммуникации: не включены")

    lines.append("")
    lines.append(f"💰 <b>ИТОГО: {format_money(total)} ₽</b>")
    lines.append("")
    lines.append("Расчёт предварительный. Точный бюджет зависит от участка, геологии и выбранных решений.")

    return "\n".join(lines)

async def send_calc_to_admin(update: Update, calc: dict, contacts_text: str | None, context: ContextTypes.DEFAULT_TYPE):
    """Отправляем тебе в личку заявку с расчётом."""
    user = update.effective_user
    uid = user.id
    uname = f"@{user.username}" if user.username else "—"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"

    text = [
        "📩 <b>Новая заявка с расчёта</b>",
        "",
        f"Пользователь: {name}",
        f"Username: {uname}",
        f"User ID: <code>{uid}</code>",
    ]
    if contacts_text:
        text.append(f"Контакты (из формы): {contacts_text}")
    text.append("")
    text.append(build_calc_text(calc))

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text="\n".join(text),
        parse_mode="HTML"
    )

# ========= КАЛЬКУЛЯТОР: ЛОГИКА =========

async def start_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск мастера расчёта."""
    context.user_data["state"] = "CALC_PROJECT_OR_CUSTOM"
    context.user_data["calc"] = {}

    keyboard = [
        ["🏡 Выбрать типовой проект"],
        ["📐 Указать свою площадь"],
        ["🔙 В главное меню"],
    ]
    await update.message.reply_text(
        "🧮 Давайте посчитаем ориентировочную стоимость дома.\n\n"
        "Сначала выберите вариант:",
        reply_markup=kb(keyboard)
    )

async def handle_calc_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str):
    """Обработка текстов во всех состояниях калькулятора."""
    text = (update.message.text or "").strip()
    calc = context.user_data.get("calc", {}) or {}
    has_contacts = context.user_data.get("has_contacts", False)

    # --- шаг 1: выбор «типовой / своя площадь» ---
    if state == "CALC_PROJECT_OR_CUSTOM":
        if text == "🏡 Выбрать типовой проект":
            calc["mode"] = "standard"
            context.user_data["calc"] = calc
            context.user_data["state"] = "CALC_CHOOSE_PROJECT"

            rows = [[name] for name in PROJECT_CHOICES]
            rows.append(["🔙 В главное меню"])
            await update.message.reply_text(
                "Выберите проект из списка:",
                reply_markup=kb(rows)
            )
            return

        if text == "📐 Указать свою площадь":
            calc["mode"] = "custom"
            context.user_data["calc"] = calc
            context.user_data["state"] = "CALC_CUSTOM_AREA"

            await update.message.reply_text(
                "Введите желаемую площадь дома в м² (только число, например: 120):",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        if text == "🔙 В главное меню":
            context.user_data["state"] = "MAIN"
            await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))
            return

        # любое другое — мягко повторить
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов кнопками ниже 👇",
            reply_markup=kb([
                ["🏡 Выбрать типовой проект"],
                ["📐 Указать свою площадь"],
                ["🔙 В главное меню"],
            ])
        )
        return

    # --- шаг 2: выбор типового проекта ---
    if state == "CALC_CHOOSE_PROJECT":
        if text == "🔙 В главное меню":
            context.user_data["state"] = "MAIN"
            await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))
            return

        if text not in PROJECT_PRICES:
            rows = [[name] for name in PROJECT_CHOICES]
            rows.append(["🔙 В главное меню"])
            await update.message.reply_text(
                "Выберите проект из списка кнопками ниже 👇",
                reply_markup=kb(rows)
            )
            return

        calc["mode"] = "standard"
        calc["project_name"] = text
        calc["area"] = parse_area_from_name(text)
        context.user_data["calc"] = calc
        context.user_data["state"] = "CALC_OPTIONS"

        # Переходим к выбору опций
        await update.message.reply_text(
            "Что включить в расчёт?\n\n"
            "Тёплый контур входит всегда.\n"
            "Выберите комбинацию опций:",
            reply_markup=kb([
                ["Только тёплый контур"],
                ["Тёплый контур + предчистовая"],
                ["Тёплый контур + коммуникации"],
                ["Тёплый контур + предчистовая + коммуникации"],
                ["🔙 В главное меню"],
            ])
        )
        return

    # --- шаг 2 для custom: ввод площади ---
    if state == "CALC_CUSTOM_AREA":
        # можно вернуться в меню командой /menu, но кнопок нет — ок
        try:
            area = int(text.replace(" ", ""))
            if area <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "Пожалуйста, введите площадь числом, например: 120"
            )
            return

        calc["area"] = area
        context.user_data["calc"] = calc
        context.user_data["state"] = "CALC_CUSTOM_FLOORS"

        await update.message.reply_text(
            f"Площадь принята: {area} м².\n\n"
            "Выберите этажность:",
            reply_markup=kb([
                ["1 этаж"],
                ["2 этажа"],
                ["🔙 В главное меню"],
            ])
        )
        return

    # --- шаг 3 для custom: выбор этажности ---
    if state == "CALC_CUSTOM_FLOORS":
        if text == "🔙 В главное меню":
            context.user_data["state"] = "MAIN"
            await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))
            return

        if text not in ("1 этаж", "2 этажа"):
            await update.message.reply_text(
                "Пожалуйста, выберите этажность кнопками ниже 👇",
                reply_markup=kb([
                    ["1 этаж"],
                    ["2 этажа"],
                    ["🔙 В главное меню"],
                ])
            )
            return

        floors = 1 if text == "1 этаж" else 2
        calc["mode"] = "custom"
        calc["floors"] = floors
        context.user_data["calc"] = calc
        context.user_data["state"] = "CALC_OPTIONS"

        await update.message.reply_text(
            "Что включить в расчёт?\n\n"
            "Тёплый контур входит всегда.\n"
            "Выберите комбинацию опций:",
            reply_markup=kb([
                ["Только тёплый контур"],
                ["Тёплый контур + предчистовая"],
                ["Тёплый контур + коммуникации"],
                ["Тёплый контур + предчистовая + коммуникации"],
                ["🔙 В главное меню"],
            ])
        )
        return

    # --- шаг с опциями (общий для standard и custom) ---
    if state == "CALC_OPTIONS":
        if text == "🔙 В главное меню":
            context.user_data["state"] = "MAIN"
            await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))
            return

        combo_map = {
            "Только тёплый контур": (False, False),
            "Тёплый контур + предчистовая": (True, False),
            "Тёплый контур + коммуникации": (False, True),
            "Тёплый контур + предчистовая + коммуникации": (True, True),
        }
        if text not in combo_map:
            await update.message.reply_text(
                "Пожалуйста, выберите вариант кнопками ниже 👇",
                reply_markup=kb([
                    ["Только тёплый контур"],
                    ["Тёплый контур + предчистовая"],
                    ["Тёплый контур + коммуникации"],
                    ["Тёплый контур + предчистовая + коммуникации"],
                    ["🔙 В главное меню"],
                ])
            )
            return

        include_pred, include_comm = combo_map[text]
        calc["include_pred"] = include_pred
        calc["include_comm"] = include_comm

        # --- считаем деньги ---
        area = calc.get("area")
        mode = calc.get("mode")

        warm_price = 0
        if mode == "standard":
            pname = calc.get("project_name")
            warm_price = PROJECT_PRICES.get(pname, 0)
        else:
            if area and calc.get("floors") == 1:
                warm_price = area * PRICE_WARM_1F
            elif area and calc.get("floors") == 2:
                warm_price = area * PRICE_WARM_2F

        pred_price = area * PRICE_PREDCHIST if (area and include_pred) else 0
        comm_price = PRICE_COMM if include_comm else 0
        total = warm_price + pred_price + comm_price

        calc["warm_price"] = warm_price
        calc["pred_price"] = pred_price
        calc["comm_price"] = comm_price
        calc["total"] = total
        context.user_data["calc"] = calc

        # --- проверка контактов ---
        if not has_contacts:
            # просим контакты, расчёт пока не показываем
            context.user_data["state"] = "CALC_CONTACTS"
            await update.message.reply_text(
                "Чтобы показать подробный расчёт, пожалуйста, напишите, как к вам обращаться "
                "и номер телефона (или удобный способ связи):\n\n"
                "Например: «Иван, +7 999 123-45-67»",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        # контакты уже есть — сразу показываем расчёт
        context.user_data["state"] = "MAIN"
        await update.message.reply_text(
            build_calc_text(calc),
            parse_mode="HTML",
            reply_markup=kb(MAIN_MENU)
        )

        contacts_text = context.user_data.get("contacts_text")
        await send_calc_to_admin(update, calc, contacts_text, context)
        return

    # --- шаг: ввод контактов (первый раз) ---
    if state == "CALC_CONTACTS":
        contacts_text = text.strip()
        if len(contacts_text) < 3:
            await update.message.reply_text(
                "Пожалуйста, напишите имя и телефон или удобный способ связи 🙂"
            )
            return

        # сохраняем контакты и флаг, что уже оставил
        context.user_data["has_contacts"] = True
        context.user_data["contacts_text"] = contacts_text

        calc = context.user_data.get("calc", {}) or {}
        if not calc:
            # На всякий случай — если что-то пошло не так
            context.user_data["state"] = "MAIN"
            await update.message.reply_text(
                "Спасибо! Контакты записал. Попробуйте запустить расчёт ещё раз через кнопку «🧮 Расчёт стоимости».",
                reply_markup=kb(MAIN_MENU)
            )
            return

        # показываем расчёт
        context.user_data["state"] = "MAIN"
        await update.message.reply_text(
            "Спасибо! Контакты записал.\nВот ваш предварительный расчёт 👇",
            reply_markup=kb(MAIN_MENU)
        )
        await update.message.reply_text(
            build_calc_text(calc),
            parse_mode="HTML"
        )

        await send_calc_to_admin(update, calc, contacts_text, context)
        return

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

    # Глобальные кнопки, которые работают из любого состояния
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if text == "🧮 Расчёт стоимости":
        return await start_calc(update, context)

    # Калькулятор: свои состояния
    if state and state.startswith("CALC_"):
        return await handle_calc_text(update, context, state)

    # Обычное поведение в главном меню
    if state == "MAIN":
        mapping = {
            "🤖 Задать вопрос ИИ": "Напишите вопрос, я постараюсь помочь (пока заглушка).",
            "👨‍💼 Связаться с менеджером": "Наш менеджер свяжется с вами: +7 (910) 864-07-37",
            # "🧮 Расчёт стоимости" здесь больше не обрабатываем текстом, только через мастер
        }
        if text in mapping:
            return await update.message.reply_text(mapping[text], reply_markup=kb(MAIN_MENU))
        return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

    # Остальные состояния (LOC_LIST / PROJ_LIST) — текст не трогаем
    return

async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()

    # Локации
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
            await context.bot.send_message(
                query.message.chat_id,
                "Выберите локацию:",
                reply_markup=make_locations_inline()
            )
        context.user_data["state"] = "LOC_LIST"
        return

    # Проекты
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
            await context.bot.send_message(
                query.message.chat_id,
                "Выберите проект:",
                reply_markup=make_projects_inline()
            )
        context.user_data["state"] = "PROJ_LIST"
        return

    # В меню
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