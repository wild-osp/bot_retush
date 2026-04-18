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

MODEL_NAME = "google/gemini-3.1-flash-image-preview"

# Специальные промпты для ритуальной печати + обычные
PROMPTS = {
    "enhance": "Восстанови старое фото: улучши резкость, убери шум, царапины и потертости, сделай чётче и чище, но НЕ меняй лицо человека и его черты. Подготовь для качественной печати.",
    
    "restore": "Профессионально восстанови старое повреждённое фото: убери трещины, пятна, царапины, выцветание. Сделай естественные цвета и хорошую резкость. Лицо и черты человека не менять. Максимальное качество для печати.",
    
    "portrait_ritual": "Сделай красивое ритуальное портретное фото: мягкое студийное освещение, естественная кожа, спокойный и достойный вид. Улучши качество, но сохрани реалистичность лица. Подготовь для печати на памятник или ритуальную продукцию.",
    
    "background": "Поменяй фон на спокойный нейтральный (светло-серый, мягкий градиент или классический тёмный), но НЕ меняй лицо, тело и одежду человека. Подходит для ритуальной печати.",
    
    "color_old": "Восстанови естественные цвета старого выцветшего фото, сделай их мягкими и приятными, улучши качество, лицо не трогай. Подготовь для печати.",
    
    "cinema": "Сделай атмосферный кинематографичный стиль с мягким светом, но сохрани естественность и реалистичность лица. Подходит для красивой ритуальной печати.",
    
    "remove_bg": "Удали фон полностью и сделай чистый белый или прозрачный фон. Лицо и тело человека оставить без изменений. Идеально для дальнейшей ритуальной верстки.",
    
    "clean": "Максимально очистить фото: убрать шум, мелкие дефекты, пыль, царапины. Сделать чистое и готовое к большой печати фото, лицо не изменять.",
}

photo_storage = {}

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Бот для ретуши ритуальных фото готов!\n\n"
        "Отправь фото (часто старые и повреждённые) и выбери нужное действие:"
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    photo_file = message.photo[-1]
    file = await bot.get_file(photo_file.file_id)
    file_bytes = await bot.download_file(file.file_path)

    user_id = message.from_user.id
    photo_storage[user_id] = file_bytes.getvalue()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Восстановить старое фото", callback_data="restore")],
        [InlineKeyboardButton(text="✨ Улучшить качество", callback_data="enhance")],
        [InlineKeyboardButton(text="🖼 Ритуальный портрет", callback_data="portrait_ritual")],
        [InlineKeyboardButton(text="🌫 Спокойный фон", callback_data="background")],
        [InlineKeyboardButton(text="🎨 Восстановить цвета", callback_data="color_old")],
        [InlineKeyboardButton(text="🧼 Максимальная очистка", callback_data="clean")],
        [InlineKeyboardButton(text="✂️ Удалить фон", callback_data="remove_bg")],
        [InlineKeyboardButton(text="🎥 Кинематографичный стиль", callback_data="cinema")],
    ])

    await message.answer("✅ Фото получено!\nВыбери, что нужно сделать для печати:", reply_markup=keyboard)

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in photo_storage:
        await callback.answer("Фото устарело, отправь заново.", show_alert=True)
        return

    prompt_key = callback.data
    prompt_text = PROMPTS.get(prompt_key, "Улучши качество фото для печати, не меняя лицо.")

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
                    "X-Title": "Ritual Retouch Bot",
                },
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                            ]
                        }
                    ],
                    "modalities": ["image", "text"],
                    "max_tokens": 2048,
                }
            )

            data = response.json()

            if "choices" in data and data["choices"]:
                message_obj = data["choices"][0].get("message", {})
                if message_obj.get("images"):
                    for img in message_obj["images"]:
                        if img.get("image_url", {}).get("url", "").startswith("data:image"):
                            b64_data = img["image_url"]["url"].split("base64,")[-1]
                            image_bytes = base64.b64decode(b64_data)
                            
                            await bot.send_photo(
                                chat_id=user_id,
                                photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
                                caption=f"✅ Готово для печати!\nПромпт: {prompt_text[:130]}..."
                            )
                            break
                    else:
                        await bot.send_message(user_id, "❌ Изображение не получено.")
                    return

            await bot.send_message(user_id, "❌ Не удалось получить результат от модели.")

    except Exception as e:
        logging.error(f"OpenRouter error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка обработки:\n{str(e)[:350]}")

    if user_id in photo_storage:
        del photo_storage[user_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
