"""
Yerdaulet AI — Telegram-бот на aiogram + OpenRouter API
Деплой: Render (polling mode)
"""

import asyncio
import os
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.enums import ChatAction

# ──────────────────────────────────────────────
# Конфигурация (из переменных окружения Render)
# ──────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-chat"          # модель на OpenRouter
MAX_TOKENS = 150                           # лимит токенов ответа
TEMPERATURE = 0.7                          # креативность
MAX_HISTORY = 5                            # последних сообщений в контексте

# ──────────────────────────────────────────────
# Хранилище состояний пользователей (в памяти)
# ──────────────────────────────────────────────
# user_data[user_id] = {"lang": "ru", "history": [...]}
user_data: dict[int, dict] = {}


def get_user(user_id: int) -> dict:
    """Возвращает данные пользователя, создаёт запись если нет."""
    if user_id not in user_data:
        user_data[user_id] = {"lang": "ru", "history": []}
    return user_data[user_id]


# ──────────────────────────────────────────────
# Клавиатура
# ──────────────────────────────────────────────

def main_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Инлайн-кнопки под каждым ответом бота."""
    lang_label = "🌐 Switch to EN" if lang == "ru" else "🌐 Switch to RU"
    clear_label = "🗑 Очистить диалог" if lang == "ru" else "🗑 Clear chat"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=lang_label, callback_data="toggle_lang"),
            InlineKeyboardButton(text=clear_label, callback_data="clear_history"),
        ]
    ])


# ──────────────────────────────────────────────
# OpenRouter API запрос
# ──────────────────────────────────────────────

async def ask_openrouter(messages: list[dict]) -> str:
    """
    Отправляет историю сообщений в OpenRouter и возвращает ответ модели.
    При ошибке возвращает строку с сообщением об ошибке.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/YerdauletAI",   # необязательно, но рекомендуется
        "X-Title": "Yerdaulet AI",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": False,   # aiogram не поддерживает SSE напрямую → False
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as e:
        print(f"[API HTTP Error] {e.response.status_code}: {e.response.text}")
        return "❌ Ошибка API, попробуй позже." if "ru" in str(messages) else "❌ API error, try again later."
    except Exception as e:
        print(f"[API Error] {e}")
        return "❌ Ошибка, попробуй позже."


# ──────────────────────────────────────────────
# Инициализация бота и диспетчера
# ──────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ──────────────────────────────────────────────
# Обработчики команд
# ──────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Приветственное сообщение с кнопками."""
    user = get_user(message.from_user.id)
    text = (
        "👋 Привет, я <b>Yerdaulet AI</b> 🤖\n"
        "Hello, I am <b>Yerdaulet AI</b> 🤖\n\n"
        "Задай мне любой вопрос — отвечу на русском или английском!\n"
        "Ask me anything — I'll reply in Russian or English!"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard(user["lang"]))


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    """Очистка истории через команду /clear."""
    user = get_user(message.from_user.id)
    user["history"].clear()
    reply = "🗑 Диалог очищен!" if user["lang"] == "ru" else "🗑 Chat cleared!"
    await message.answer(reply, reply_markup=main_keyboard(user["lang"]))


# ──────────────────────────────────────────────
# Обработчики кнопок
# ──────────────────────────────────────────────

@dp.callback_query(F.data == "toggle_lang")
async def toggle_lang(call: CallbackQuery):
    """Переключение языка интерфейса."""
    user = get_user(call.from_user.id)
    user["lang"] = "en" if user["lang"] == "ru" else "ru"
    reply = "🌐 Язык переключён на русский!" if user["lang"] == "ru" else "🌐 Language switched to English!"
    await call.answer(reply, show_alert=False)
    await call.message.edit_reply_markup(reply_markup=main_keyboard(user["lang"]))


@dp.callback_query(F.data == "clear_history")
async def clear_history(call: CallbackQuery):
    """Очистка истории через кнопку."""
    user = get_user(call.from_user.id)
    user["history"].clear()
    reply = "🗑 Диалог очищен!" if user["lang"] == "ru" else "🗑 Chat cleared!"
    await call.answer(reply, show_alert=True)


# ──────────────────────────────────────────────
# Основной обработчик сообщений
# ──────────────────────────────────────────────

@dp.message(F.text)
async def handle_message(message: Message):
    """
    Принимает текст пользователя, добавляет в историю,
    отправляет в OpenRouter и возвращает ответ.
    """
    user = get_user(message.from_user.id)
    lang = user["lang"]

    # Показываем индикатор "печатает..."
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    # Системный промпт — короткий для скорости
    system_prompt = (
        "You are Yerdaulet AI, a helpful assistant. "
        "Reply in the same language the user writes in. "
        "Be concise and friendly."
    )

    # Добавляем сообщение пользователя в историю
    user["history"].append({"role": "user", "content": message.text})

    # Обрезаем до последних MAX_HISTORY сообщений
    if len(user["history"]) > MAX_HISTORY * 2:
        user["history"] = user["history"][-(MAX_HISTORY * 2):]

    # Формируем payload для API
    messages = [{"role": "system", "content": system_prompt}] + user["history"]

    # Запрос к OpenRouter
    reply_text = await ask_openrouter(messages)

    # Добавляем ответ ассистента в историю
    user["history"].append({"role": "assistant", "content": reply_text})

    # Отправляем ответ с кнопками
    await message.answer(reply_text, reply_markup=main_keyboard(lang))


# ──────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────

async def main():
    print("🤖 Yerdaulet AI запущен (polling)...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
