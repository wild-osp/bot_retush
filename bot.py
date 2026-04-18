import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import os
import time

# Google SDK
from google import genai
from google.genai import types as genai_types

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# Самая стабильная бесплатная модель для ретуши
MODEL_NAME = "gemini-2.5-flash-image"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

PROMPTS = {
    "enhance": "Улучши качество фото, сделай его чётче, красивее и профессиональнее, но НЕ меняй лицо человека и его черты.",
    "background": "Поменяй фон на современный минималистичный или красивый (природа, студия, город), но НЕ меняй лицо, тело и одежду человека.",
    "portrait": "Сделай профессиональный студийный портрет: улучши кожу, освещение, цвета, но НЕ меняй черты лица.",
    "color": "Сделай цвета более яркими и естественными, улучши общее качество фото, лицо не трогай.",
    "cinema": "Преврати фото в кинематографичный стиль с красивым светом и атмосферой, но оставь лицо реалистичным.",
    "remove_bg": "Удали фон полностью и сделай прозрачный фон (или чисто белый), лицо и тело оставь без изменений.",
}

photo_storage = {}

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Это бот-ретушёр на Gemini Nano Banana.\n\n"
        "Отправь фото → выбери кнопку.\n"
        "Лимит бесплатный, поэтому может быть ожидание."
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
        [InlineKeyboardButton(text="🖼 Профессиональный портрет", callback_data="portrait")],
        [InlineKeyboardButton(text="🌈 Яркие цвета", callback_data="color")],
        [InlineKeyboardButton(text="🎥 Кинематографичный стиль", callback_data="cinema")],
        [InlineKeyboardButton(text="✂️ Удалить фон", callback_data="remove_bg")],
    ])

    await message.answer("✅ Фото получено!\nВыбери действие:", reply_markup=keyboard)

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in photo_storage:
        await callback.answer("Фото устарело, отправь заново.", show_alert=True)
        return

    prompt_key = callback.data
    prompt_text = PROMPTS.get(prompt_key, "Улучши качество фото, не меняя лицо.")

    await callback.answer("🔄 Обрабатываю... (может занять 10–30 сек)")

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
                    caption=f"✅ Готово!\nПромпт: {prompt_text[:100]}..."
                )
                break

    except Exception as e:
        error = str(e)
        logging.error(f"Gemini error: {error}")
        if "429" in error or "quota" in error.lower() or "RESOURCE_EXHAUSTED" in error:
            await bot.send_message(
                user_id,
                "❌ Лимит бесплатных запросов исчерпан на сегодня.\n\n"
                "Подожди до завтра (квота сбрасывается примерно в 00:00 по Тихоокеанскому времени) "
                "или создай новый Google-аккаунт и новый API-ключ."
            )
        else:
            await bot.send_message(user_id, f"❌ Ошибка: {error[:300]}")

    # Очистка
    if user_id in photo_storage:
        del photo_storage[user_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
