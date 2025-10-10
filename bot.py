import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# === 🔧 НАСТРОЙКИ ===
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # ⚠️ ВСТАВЬ СВОЙ ТОКЕН!
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === СОЗДАЁМ ПРИЛОЖЕНИЕ Telegram ===
application = Application.builder().token(TOKEN).build()

# === ОБРАБОТЧИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🏗 Узнать стоимость строительства", callback_data="price"),
            InlineKeyboardButton("📂 Наши проекты", callback_data="projects"),
        ],
        [
            InlineKeyboardButton("📞 Контакты", callback_data="contacts"),
            InlineKeyboardButton("ℹ️ О компании", callback_data="about"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я бот **MR.House** — агентства загородной недвижимости.\n\n"
        "Выберите интересующий раздел ниже 👇",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

async def debug(update: Update, context: ContextTypes.DEFAULT
