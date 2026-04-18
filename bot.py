import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import os
import time

from google import genai
from google.genai import types as genai_types

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# Самая стабильная модель на апрель 2026 для бесплатного tier
MODEL_NAME = "gemini-2.5-flash-image"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

PROMPTS = {
    "enhance": "Улучши качество фото, сделай чётче и красивее, но НЕ меняй лицо и черты человека.",
    "background": "Поменяй фон на красивый современный (студия, природа, минимализм), но НЕ меняй лицо, тело и одежду.",
    "portrait": "Сделай профессиональный портрет: улучши кожу, освещение, но НЕ меняй черты лица.",
    "color": "Сделай цвета ярче и естественнее, улучши качество, лицо не трогай.",
    "cinema": "Преврати в кинематографичный стиль с красивым светом, лицо оставь реалистичным.",
    "remove_bg": "Удали фон полностью, сделай прозрачный или белый, лицо и тело не меняй.",
}

photo_storage = {}

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Бот-ретушёр запущен!\n\n"
        "Отправь фото → выбери кнопку.\n"
        "Если лимит Gemini кончился — подожди или создай новый ключ."
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    photo_file = message.photo[-1]
    file = await bot.get_file(photo_file.file_id)
    file_bytes = await bot.download_file(file.file_path)

    photo_storage[message.from_user.id] = file_bytes.getvalue()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Улучшить качество", callback_data="enhance")],
        [InlineKeyboardButton(text="🌄 Изменить фон", callback_data="background")],
        [InlineKeyboardButton(text="🖼 Портрет", callback_data="portrait")],
        [InlineKeyboardButton(text="🌈 Яркие цвета", callback_data="color")],
        [InlineKeyboardButton(text="🎥 Кино стиль", callback_data="cinema")],
        [InlineKeyboardButton(text="✂️ Удалить фон", callback_data="remove_bg")],
    ])

    await message.answer("✅ Фото получено! Выбери действие:", reply_markup=keyboard)

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in photo_storage:
        await callback.answer("Фото устарело, отправь заново.", show_alert=True)
        return

    prompt_key = callback.data
    prompt_text = PROMPTS.get(prompt_key, "Улучши качество фото.")

    await callback.answer("🔄 Обрабатываю... (может быть задержка при лимите)")

    photo_bytes = photo_storage[user_id]

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt_text,
                genai_types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg")
            ],
            config=genai_types.GenerateContentConfig(temperature=0.7)
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                await bot.send_photo(
                    chat_id=user_id,
                    photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
                    caption=f"✅ Готово с Gemini 2.5 Flash Image!\nПромпт: {prompt_text[:100]}..."
                )
                break

    except Exception as e:
        error = str(e)
        if "429" in error or "quota" in error.lower() or "RESOURCE_EXHAUSTED" in error:
            await bot.send_message(
                user_id,
                "❌ Лимит Gemini исчерпан на сегодня.\n\n"
                "Варианты:\n"
                "1. Подожди до завтра (квота сбрасывается ~00:00 UTC)\n"
                "2. Создай новый API-ключ в https://aistudio.google.com/app/apikey\n"
                "3. Напиши мне — перейдём на Grok Imagine (xAI)"
            )
        else:
            await bot.send_message(user_id, f"❌ Ошибка: {error[:300]}")

    if user_id in photo_storage:
        del photo_storage[user_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
