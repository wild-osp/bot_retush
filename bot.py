import asyncio
import logging
import base64
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

MODEL_NAME = "google/gemini-3.1-flash-image-preview"

photo_storage = {}      # оригинальное фото
last_result = {}        # последнее обработанное фото
processing = {}         # защита от двойного нажатия
waiting_for = {}        # что сейчас ожидает бот от пользователя

# ================= ПРОМПТЫ =================
PROMPTS = {
    "restore": "Профессионально восстанови старое или повреждённое фото. Убери царапины, шум, пятна, трещины, выцветание. Сделай чёткость и естественные цвета. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА ЧЕЛОВЕКА. Сохрани полное сходство.",
    
    "restore_extend": "Восстанови старое фото и немного расширь его (дорисуй плечи и фон). НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА. Всё должно быть пропорционально.",
    
    "ritual_portrait": "Сделай красивое ритуальное портретное фото с мягким студийным освещением и достойным видом. Улучши качество. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА ЧЕЛОВЕКА.",
    
    "ritual_with_ribbon": "Сделай ритуальный портрет: улучши качество, сделай мягкое освещение, достойный вид и добавь в ПРАВЫЙ НИЖНИЙ УГОЛ чёрную траурную ленту по диагонали. Лента простая, аккуратная, без бантиков и цветов. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА.",
    
    "ritual_strict": "Сделай ритуальный портрет со строгим фоном и строгой одеждой. Никаких лишних элементов. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА.",
    
    "bg_auto": "Поменяй фон на спокойный нейтральный фон, подходящий для ритуальной печати. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ, ОДЕЖДУ И ЧЕРТЫ ЛИЦА.",
    
    "clothes_auto": "Поменяй одежду на строгую траурную одежду. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА. Одежда должна быть пропорциональной.",
}

def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔧 Восстановление старого фото", callback_data="menu:restore")
    kb.button(text="🖼 Ритуальный портрет", callback_data="menu:ritual")
    kb.button(text="🌫 Смена фона", callback_data="menu:bg")
    kb.button(text="👔 Смена одежды", callback_data="menu:clothes")
    kb.button(text="🧼 Максимальная очистка", callback_data="clean")
    kb.button(text="🎨 Восстановить цвета", callback_data="color_restore")
    kb.button(text="✍️ Свой промпт", callback_data="custom")
    kb.button(text="🔄 Доработать последнее фото", callback_data="redo_last")
    kb.adjust(1)
    return kb.as_markup()

def restore_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Восстановить старое фото", callback_data="restore")
    kb.button(text="Восстановить + расширить размер", callback_data="restore_extend")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def ritual_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Ритуальный портрет", callback_data="ritual_portrait")
    kb.button(text="Ритуальный портрет + лента", callback_data="ritual_with_ribbon")
    kb.button(text="Ритуальный портрет + строгий фон и одежда", callback_data="ritual_strict")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def bg_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Автоподбор спокойного фона", callback_data="bg_auto")
    kb.button(text="Смена фона по моему описанию", callback_data="bg_custom")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def clothes_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Автоподбор строгой одежды", callback_data="clothes_auto")
    kb.button(text="Смена одежды по моему описанию", callback_data="clothes_custom")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Ритуальный ретушёр готов!\nОтправь фото и выбирай действие.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    file_bytes = await bot.download_file(file.file_path)

    photo_storage[user_id] = file_bytes.getvalue()
    last_result[user_id] = None
    processing[user_id] = False
    waiting_for[user_id] = None

    await message.answer("✅ Фото получено!\nЧто нужно сделать для траурной печати?", reply_markup=main_keyboard())

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if user_id in processing and processing.get(user_id):
        await callback.answer("⏳ Уже обрабатывается, подожди...", show_alert=True)
        return

    if user_id not in photo_storage:
        await callback.answer("Фото устарело. Отправь заново.", show_alert=True)
        return

    # Открытие подменю
    if data.startswith("menu:"):
        if data == "menu:restore":
            await callback.message.edit_reply_markup(reply_markup=restore_keyboard())
        elif data == "menu:ritual":
            await callback.message.edit_reply_markup(reply_markup=ritual_keyboard())
        elif data == "menu:bg":
            await callback.message.edit_reply_markup(reply_markup=bg_keyboard())
        elif data == "menu:clothes":
            await callback.message.edit_reply_markup(reply_markup=clothes_keyboard())
        return

    if data == "back:main":
        await callback.message.edit_reply_markup(reply_markup=main_keyboard())
        return

    # === Кнопки, которые требуют ввода текста ===
    if data in ["bg_custom", "clothes_custom", "custom"]:
        if data == "bg_custom":
            msg = "Напиши, какой фон хочешь увидеть (например: лес, студия, небо, градиент и т.д.)"
        elif data == "clothes_custom":
            msg = "Напиши, какую одежду хочешь (например: тёмный костюм, чёрное платье, строгий пиджак и т.д.)"
        else:
            msg = "Напиши свой промпт. Бот автоматически добавит защиту лица в конец."

        await callback.message.edit_text(msg)
        waiting_for[user_id] = data
        return

    # === Обычные кнопки с готовыми промптами ===
    processing[user_id] = True
    await callback.message.edit_text("🔄 Обрабатываю... (может занять 15–40 секунд)")

    prompt_key = data
    prompt_text = PROMPTS.get(prompt_key, "Улучши качество фото, не меняя лицо.")

    # Выбираем какое фото обрабатывать
    photo_bytes = last_result.get(user_id) if prompt_key == "redo_last" and last_result.get(user_id) else photo_storage[user_id]
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
                        url = img.get("image_url", {}).get("url", "")
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

            await bot.send_message(user_id, "❌ Не удалось получить изображение.")

    except Exception as e:
        logging.error(f"Error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:300]}")

    processing[user_id] = False

# ================= ОБРАБОТКА ТЕКСТА (Свой промпт, фон по описанию, одежда по описанию) =================
@dp.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if user_id not in waiting_for or not waiting_for.get(user_id):
        return

    user_text = message.text.strip()
    action = waiting_for[user_id]
    waiting_for[user_id] = None

    if not user_text:
        await message.answer("Промпт не может быть пустым. Попробуй ещё раз.")
        return

    await message.answer("🔄 Обрабатываю по твоему описанию...")

    if action == "custom":
        full_prompt = f"{user_text}. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА ЧЕЛОВЕКА. Сохрани максимальное сходство. No bows, no flowers, no decorations."
    elif action == "bg_custom":
        full_prompt = f"Поменяй фон на: {user_text}. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ, ОДЕЖДУ И ЧЕРТЫ ЛИЦА."
    elif action == "clothes_custom":
        full_prompt = f"Поменяй одежду на: {user_text}. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА. Одежда должна быть пропорциональной."
    else:
        full_prompt = user_text

    # Пока заглушка — полная обработка будет добавлена в следующей версии
    # (чтобы не ломать стабильность)
    await message.answer(f"✅ Промпт принят:\n\n{full_prompt[:250]}...\n\nОбработка по тексту будет полностью работать в следующей версии.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
