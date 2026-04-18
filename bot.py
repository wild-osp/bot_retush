import asyncio
import logging
import os
import base64
from io import BytesIO

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")   # ← твой ключ с openrouter.ai

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Лучшая модель для ретуши с сохранением лица (Nano Banana 2)
MODEL_NAME = "google/gemini-3.1-flash-image-preview"   # Nano Banana 2

# Можно поменять на "google/gemini-2.5-flash-image" если будет дороже/медленнее

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
        "👋 Бот-ретушёр запущен на **OpenRouter + Nano Banana 2**!\n\n"
        "У тебя есть баланс — отлично!\n"
        "Отправь фото и выбери действие."
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

    await callback.answer("🔄 Обрабатываю через Nano Banana 2 (OpenRouter)...")

    photo_bytes = photo_storage[user_id]
    base64_image = base64.b64encode(photo_bytes).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://t.me",   # можно оставить или поменять
                    "X-Title": "Telegram Retouch Bot",
                },
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                                }
                            ]
                        }
                    ],
                    "max_tokens": 2048,
                }
            )

            data = response.json()

            if "choices" in data and data["choices"]:
                message_content = data["choices"][0]["message"]["content"]
                
                # OpenRouter возвращает base64 изображения в ответе для image-моделей
                if "data:" in message_content and "base64" in message_content:
                    # Извлекаем base64 часть
                    b64_data = message_content.split("base64,")[-1].split('"')[0]
                    image_bytes = base64.b64decode(b64_data)
                    
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
                        caption=f"✅ Готово через OpenRouter (Nano Banana 2)!\nПромпт: {prompt_text[:100]}..."
                    )
                else:
                    await bot.send_message(user_id, "❌ Модель не вернула изображение. Попробуй другой промпт.")
            else:
                error_msg = data.get("error", {}).get("message", str(data))
                await bot.send_message(user_id, f"❌ Ошибка OpenRouter:\n{error_msg[:400]}")

    except Exception as e:
        logging.error(f"OpenRouter error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка при обработке: {str(e)[:300]}")

    # Очистка
    if user_id in photo_storage:
        del photo_storage[user_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
