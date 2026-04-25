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

photo_storage = {}
last_result = {}
processing = {}

# ================= ПРОМПТЫ (сильная защита от рамок) =================
PROMPTS = {
    "ritual_with_ribbon": "Улучши качество фото, сделай мягкое студийное освещение, естественную кожу и достойный вид. Добавь в ПРАВЫЙ НИЖНИЙ УГОЛ только простую чёрную траурную ленту по диагонали. Лента аккуратная, без бантиков, без цветов. Сделай строгий нейтральный фон. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА ЧЕЛОВЕКА. ЗАПРЕЩЕНО добавлять любые рамки, овалы, золотые элементы, текст, подписи или украшения.",
    
    "restore": "Профессионально восстанови старое фото. Убери царапины, шум, пятна. Сделай чёткость. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА.",
    
    "clean": "Максимально очисти фото от шума и дефектов. НЕ ИЗМЕНЯЙ ЛИЦО.",
}

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Ритуальный портрет + лента (нижний угол)", callback_data="ritual_with_ribbon")],
        [InlineKeyboardButton(text="🔧 Восстановить старое фото", callback_data="restore")],
        [InlineKeyboardButton(text="🧼 Максимальная очистка", callback_data="clean")],
        [InlineKeyboardButton(text="✍️ Свой промпт", callback_data="custom")],
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Бот запущен!\n\n"
        "Отправь фото и выбери действие.\n"
        "Лицо защищено, рамки запрещены."
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    file_bytes = await bot.download_file(file.file_path)

    photo_storage[user_id] = file_bytes.getvalue()
    last_result[user_id] = None

    await message.answer("✅ Фото получено!\nЧто делать?", reply_markup=main_keyboard())

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if user_id in processing and processing.get(user_id):
        await callback.answer("⏳ Уже обрабатывается, подожди...", show_alert=True)
        return

    if user_id not in photo_storage:
        await callback.answer("Фото устарело.", show_alert=True)
        return

    processing[user_id] = True
    await callback.message.edit_text("🔄 Обрабатываю... (15–40 секунд)")

    prompt_text = PROMPTS.get(data, "Улучши качество фото, не меняя лицо.")

    if data == "custom":
        await callback.message.edit_text("✍️ Напиши свой промпт:")
        processing[user_id] = False
        return

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
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}],
                    "modalities": ["image", "text"],
                    "max_tokens": 2048,
                }
            )

            data_json = response.json()

            if "choices" in data_json and data_json["choices"]:
                msg = data_json["choices"][0].get("message", {})
                if msg.get("images"):
                    for img in msg["images"]:
                        url = img.get("image_url", {}).get("url", "") or img.get("url", "")
                        if url.startswith("data:image"):
                            result_bytes = base64.b64decode(url.split("base64,")[-1])
                            last_result[user_id] = result_bytes

                            await bot.send_media_group(
                                chat_id=user_id,
                                media=[
                                    types.InputMediaPhoto(types.BufferedInputFile(photo_bytes, "original.jpg"), caption="📸 Оригинал"),
                                    types.InputMediaPhoto(types.BufferedInputFile(result_bytes, "result.jpg"), caption="✅ Готово для печати")
                                ]
                            )
                            processing[user_id] = False
                            return

            await bot.send_message(user_id, "❌ Не удалось получить изображение. Попробуй ещё раз.")

    except Exception as e:
        logging.error(f"Error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:300]}")

    processing[user_id] = False

@dp.message()
async def handle_text(message: types.Message):
    await message.answer("✅ Промпт принят. (Пока обработка по тексту упрощена)")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
