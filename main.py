import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pyrogram import Client

# Данные берутся из настроек хостинга (Environment Variables)
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

db = {
    "recipients": [], 
    "text": "Здравствуйте, меня заинтересовал ваш нфт...",
    "interval": 3.0,
    "is_running": False
}

class Form(StatesGroup):
    waiting_for_phone = State()
    waiting_for_tg_code = State()
    waiting_for_2fa = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
clients = [] 
temp_auth = {}

def get_main_menu():
    text = (
        f"📩 **МЕНЮ РАССЫЛКИ**\n\n"
        f"👥 Аккаунтов в сети: {len(clients)}\n"
        f"📋 В очереди: {len(db['recipients'])}\n"
        f"⏱ Интервал: {db['interval']} сек\n"
        f"📊 Статус: {'🟢 ЗАПУЩЕНА' if db['is_running'] else '🔴 ОСТАНОВЛЕНА'}"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="👥 Добавить аккаунт", callback_data="add_acc"))
    label = "⏹ Остановить" if db['is_running'] else "▶️ ЗАПУСТИТЬ"
    builder.row(types.InlineKeyboardButton(text=label, callback_data="toggle"))
    builder.row(types.InlineKeyboardButton(text="🗑 Очистить очередь", callback_data="clear_queue"))
    return text, builder.as_markup()

@dp.message(F.text.contains("@"))
async def add_users(message: types.Message):
    added = 0
    for word in message.text.split():
        if word.startswith("@"):
            user = word.strip(",.;!")
            if {"user_id": user} not in db['recipients']:
                db['recipients'].append({"user_id": user})
                added += 1
    await message.answer(f"✅ Добавлено {added} чел. Всего в очереди: {len(db['recipients'])}")

async def broadcaster(msg_obj):
    acc_idx = 0
    while db['is_running'] and db['recipients']:
        target = db['recipients'].pop(0) # БЕРЕМ ПЕРВОГО И УДАЛЯЕМ
        client = clients[acc_idx]
        try:
            await client.send_message(target['user_id'], db['text'])
        except Exception as e:
            logging.error(f"Ошибка {target['user_id']}: {e}")
        
        acc_idx = (acc_idx + 1) % len(clients)
        await asyncio.sleep(db['interval'])

    db['is_running'] = False
    await msg_obj.answer("🏁 Рассылка завершена или список пуст!")

@dp.callback_query(F.data == "toggle")
async def toggle_process(callback: types.Callback_query):
    if not clients: return await callback.answer("❌ Нет аккаунтов!", show_alert=True)
    if not db['recipients']: return await callback.answer("❌ Список пуст!", show_alert=True)
    db['is_running'] = not db['is_running']
    if db['is_running']: asyncio.create_task(broadcaster(callback.message))
    t, kb = get_main_menu()
    await callback.message.edit_text(t, reply_markup=kb, parse_mode="Markdown")

@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    t, kb = get_main_menu()
    await message.answer(t, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "add_acc")
async def start_auth(callback: types.Callback_query, state: FSMContext):
    await state.set_state(Form.waiting_for_phone)
    await callback.message.answer("Введите номер (+7...):")

@dp.message(Form.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    c = Client(f"acc_{len(clients)}", API_ID, API_HASH, workdir="./")
    await c.connect()
    code = await c.send_code(phone)
    temp_auth[message.from_user.id] = {"c": c, "p": phone, "h": code.phone_code_hash}
    await state.set_state(Form.waiting_for_tg_code)
    await message.answer("Код из ТГ:")

@dp.message(Form.waiting_for_tg_code)
async def process_code(message: types.Message, state: FSMContext):
    data = temp_auth[message.from_user.id]
    try:
        await data["c"].sign_in(data["p"], data["h"], message.text.strip())
        clients.append(data["c"])
        await message.answer("✅ Аккаунт готов!")
        await state.clear()
    except Exception as e: await message.answer(f"Ошибка (возможно 2FA): {e}")

async def main():
    for f in os.listdir("./"):
        if f.endswith(".session"):
            c = Client(f.replace(".session", ""), API_ID, API_HASH, workdir="./")
            await c.start()
            clients.append(c)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
  
