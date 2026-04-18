import asyncio
import logging
import base64
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Nano Banana 2 — лучшая модель для ретуши с сохранением лица
MODEL_NAME = "google/gemini-3.1-flash-image-preview"

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
        "👋 Бот на **OpenRouter + Nano Banana 2** готов!\n\n"
        "Отправь фото и выбери кнопку. Баланс у тебя есть — должно работать."
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

    await callback.answer("🔄 Обрабатываю через Nano Banana 2...")

    photo_bytes = photo_storage[user_id]
    base64_image = base64.b64encode(photo_bytes).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://t.me",
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

            # Новый парсинг ответа OpenRouter для image-моделей
            if "choices" in data and data["choices"]:
                message_obj = data["choices"][0].get("message", {})
                
                # Вариант 1: изображение в поле images
                if "images" in message_obj and message_obj["images"]:
                    image_url = message_obj["images"][0]["image_url"]["url"]
                    if image_url.startswith("data:image"):
                        # base64 data URL
                        b64_data = image_url.split("base64,")[-1]
                        image_bytes = base64.b64decode(b64_data)
                        await bot.send_photo(
                            chat_id=user_id,
                            photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
                            caption=f"✅ Готово! Nano Banana 2 (OpenRouter)\nПромпт: {prompt_text[:110]}..."
                        )
                        return

                # Вариант 2: изображение внутри content (иногда приходит так)
                content = message_obj.get("content")
                if isinstance(content, str) and "base64" in content:
                    b64_data = content.split("base64,")[-1].split('"')[0] if '"' in content else content.split("base64,")[-1]
                    image_bytes = base64.b64decode(b64_data)
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
                        caption=f"✅ Готово! Nano Banana 2\nПромпт: {prompt_text[:110]}..."
                    )
                    return

            # Если ничего не нашли
            error_msg = data.get("error", {}).get("message") or str(data)[:500]
            await bot.send_message(user_id, f"❌ Не удалось получить изображение:\n{error_msg}")

    except Exception as e:
        logging.error(f"OpenRouter error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:400]}")

    # Очистка
    if user_id in photo_storage:
        del photo_storage[user_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
