import asyncio
import re
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os

# ========== КОНФИГ ==========
TOKEN = "8875140720:AAH3qzwBAJ7E7rpl9Zs0tuinSXzYdp-hl5Q"
ADMIN_ID = 8935740667

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wl_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            source TEXT NOT NULL,
            friend_nick TEXT,
            plans TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS revive_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(nickname)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approved (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT,
            approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            reply TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def is_already_applied_wl(user_id: int) -> bool:
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM wl_applications WHERE user_id = ? AND status = "pending"', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def is_already_applied_revive(nickname: str) -> bool:
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM revive_applications WHERE nickname = ? AND status = "pending"', (nickname,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def save_wl_application(user_id, user_name, name, age, nickname, source, friend_nick, plans):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO wl_applications (user_id, user_name, name, age, nickname, source, friend_nick, plans)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, user_name, name, age, nickname, source, friend_nick, plans))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def save_revive_application(nickname, user_id, user_name):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO revive_applications (nickname, user_id, user_name)
            VALUES (?, ?, ?)
        ''', (nickname, user_id, user_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_wl_status(user_id, status):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE wl_applications SET status = ? WHERE user_id = ?', (status, user_id))
    if status == 'approved':
        cursor.execute('INSERT OR REPLACE INTO approved (user_id, nickname) VALUES (?, (SELECT nickname FROM wl_applications WHERE user_id = ?))', (user_id, user_id))
    conn.commit()
    conn.close()

def update_revive_status(nickname, status):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE revive_applications SET status = ? WHERE nickname = ?', (status, nickname))
    conn.commit()
    conn.close()

def get_pending_count():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM wl_applications WHERE status = "pending"')
    count = cursor.fetchone()[0]
    conn.close()
    return count

init_db()

# ========== FSM ==========
class WLForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_nickname = State()
    waiting_for_source = State()
    waiting_for_friend_nick = State()
    waiting_for_plans = State()

class ReviveForm(StatesGroup):
    waiting_for_nickname = State()

class SupportForm(StatesGroup):
    waiting_for_message = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📜 Правила сервера", callback_data="btn_rules")
    kb.button(text="📝 Подать анкету в Вайт-лист", callback_data="btn_wl")
    kb.button(text="💀 Вторая Жизнь (30₽)", callback_data="btn_rv")
    kb.button(text="🆘 Помощник", callback_data="btn_support")
    kb.button(text="ℹ️ О проекте", callback_data="btn_about")
    kb.adjust(1)
    return kb.as_markup()

def get_back_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад в меню", callback_data="btn_menu")
    return kb.as_markup()

def get_support_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Написать админу", callback_data="btn_chat_admin")
    kb.button(text="❓ Частые вопросы", callback_data="btn_faq")
    kb.button(text="🔙 Назад", callback_data="btn_menu")
    kb.adjust(1)
    return kb.as_markup()

def is_valid_nickname(nick):
    return bool(re.match(r"^[a-zA-Z0-9_]{3,16}$", nick))

# ========== ОТПРАВКА АДМИНУ ==========
async def send_wl_to_admin(user_id, user_name, name, age, nickname, source, friend_nick, plans):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"wl_app_{user_id}")
    kb.button(text="❌ Отклонить", callback_data=f"wl_deny_{user_id}")
    
    text = f"🔔 **НОВАЯ АНКЕТА В ВАЙТ-ЛИСТ!**\n\n"
    text += f"👤 **Имя**: {name}\n"
    text += f"📅 **Возраст**: {age}\n"
    text += f"🎮 **Ник в Minecraft**: `{nickname}`\n"
    text += f"📢 **Откуда узнал**: {source}\n"
    if friend_nick:
        text += f"👥 **Друг**: {friend_nick}\n"
    text += f"🎯 **Чем займётся**: {plans}\n\n"
    text += f"🆔 **ID**: `{user_id}`\n"
    text += f"📛 **Username**: @{user_name or 'нет'}\n"
    text += f"📊 **В очереди**: {get_pending_count()}"
    
    await bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=kb.as_markup())

async def send_revive_to_admin(nickname, user_id, user_name):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить разбан", callback_data=f"rv_app_{nickname}_{user_id}")
    kb.button(text="❌ Отклонить", callback_data=f"rv_deny_{nickname}_{user_id}")
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 **ЗАЯВКА НА РАЗБАН (Вторая жизнь)**\n\n"
             f"🎮 **Ник**: `{nickname}`\n"
             f"🆔 **ID**: `{user_id}`\n"
             f"📛 **Username**: @{user_name or 'нет'}\n\n"
             f"💰 Проверь карту `2203 8302 2268 9342`",
        reply_markup=kb.as_markup()
    )

# ========== КОМАНДА /START ==========
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✨ **Добро пожаловать на AhilesVanilla!** ✨\n\n"
        "🎮 Хардкорный сервер с одной жизнью\n"
        "🎙️ Голосовой чат\n\n"
        "📝 **Чтобы попасть на сервер - заполни анкету!**\n\n"
        "👇 Выбери действие:",
        reply_markup=get_main_menu()
    )

@dp.callback_query(F.data == "btn_menu")
async def go_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("✨ Главное меню:", reply_markup=get_main_menu())

@dp.callback_query(F.data == "btn_about")
async def show_about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **О проекте AhilesVanilla**\n\n"
        "🎮 Режим: Хардкор (1 жизнь)\n"
        "🎙️ Голосовой чат: Simple Voice Chat\n"
        "🛡️ Защита: Grim Anticheat + Anti-Xray\n"
        "💰 Вторая жизнь: 30₽\n"
        "👑 Админ: Ahiles\n\n"
        "💬 По вопросам: @ahiles_support",
        reply_markup=get_back_menu()
    )

# ЭТО ТОЛЬКО СЕКЦИЯ С ПРАВИЛАМИ (не весь бот!)
# Найди в своём коде функцию show_rules и замени её на эту:

@dp.callback_query(F.data == "btn_rules")
async def show_rules(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📜 **ПРАВИЛА СЕРВЕРА AhilesVanilla**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ **Никаких читов!**\n"
        "   → Grim Anticheat + Anti-Xray\n"
        "   → Нарушение = вечный бан\n\n"
        "2️⃣ **Цени свою жизнь**\n"
        "   → Смерть = автоматический бан\n"
        "   → Купить вторую жизнь за 30₽\n\n"
        "3️⃣ **Оружие - Булава**\n"
        "   → Максимум 2 булавы на игрока\n"
        "   → Чары на булаву ЗАПРЕЩЕНЫ\n"
        "   → Булаву можно хранить в сундуках\n\n"
        "4️⃣ **Без гриферства**\n"
        "   → Приватов нет → играем честно\n"
        "   → Взаимопомощь приветствуется!\n\n"
        "5️⃣ **Голосовой чат**\n"
        "   → Общаться можно в VC\n"
        "   → Без токсичности!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚔️ **Удачных боёв!** ⚔️",
        reply_markup=get_back_menu()
    )
    
# ========== ВАЙТ-ЛИСТ (АНКЕТА) ==========
@dp.callback_query(F.data == "btn_wl")
async def start_wl(callback: types.CallbackQuery, state: FSMContext):
    if is_already_applied_wl(callback.from_user.id):
        await callback.answer("⚠️ У тебя уже есть активная заявка!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 **Анкета в Вайт-лист**\n\n"
        "Для начала напиши своё **настоящее имя**:"
    )
    await state.set_state(WLForm.waiting_for_name)

@dp.message(WLForm.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    if len(message.text) < 2:
        await message.answer("❌ Слишком короткое имя! Напиши нормально:")
        return
    await state.update_data(name=message.text.strip())
    await message.answer("📅 Теперь напиши свой **возраст** (только число):")
    await state.set_state(WLForm.waiting_for_age)

@dp.message(WLForm.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if age < 10:
            await message.answer("❌ Извини, сервер 10+! Ты не проходишь по возрасту.")
            await state.clear()
            return
        if age > 100:
            await message.answer("❌ Это нереальный возраст! Напиши правду:")
            return
        await state.update_data(age=age)
        await message.answer("🎮 Напиши свой **Minecraft ник** (только латиница, цифры, _):\n\nПример: `Ahiles_2024`")
        await state.set_state(WLForm.waiting_for_nickname)
    except ValueError:
        await message.answer("❌ Напиши число! Сколько тебе лет?")

@dp.message(WLForm.waiting_for_nickname)
async def process_wl_nickname(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    if not is_valid_nickname(nickname):
        await message.answer("❌ Неверный формат! Ник: 3-16 символов, латиница/цифры/_")
        return
    await state.update_data(nickname=nickname)
    await message.answer("📢 Откуда ты узнал о сервере?\n\nВарианты: TikTok, YouTube, от друга, реклама, другое")
    await state.set_state(WLForm.waiting_for_source)

@dp.message(WLForm.waiting_for_source)
async def process_source(message: types.Message, state: FSMContext):
    source = message.text.strip()
    await state.update_data(source=source)
    
    if "друг" in source.lower():
        await message.answer("👥 Напиши ник друга, который тебя пригласил:")
        await state.set_state(WLForm.waiting_for_friend_nick)
    else:
        await state.update_data(friend_nick=None)
        await message.answer("🎯 Чем ты планируешь заниматься на сервере?\n\n(строительство, пвп, фермы, исследования и т.д.)")
        await state.set_state(WLForm.waiting_for_plans)

@dp.message(WLForm.waiting_for_friend_nick)
async def process_friend(message: types.Message, state: FSMContext):
    await state.update_data(friend_nick=message.text.strip())
    await message.answer("🎯 Чем ты планируешь заниматься на сервере?\n\n(строительство, пвп, фермы, исследования и т.д.)")
    await state.set_state(WLForm.waiting_for_plans)

@dp.message(WLForm.waiting_for_plans)
async def process_plans(message: types.Message, state: FSMContext):
    plans = message.text.strip()
    if len(plans) < 5:
        await message.answer("❌ Напиши подробнее, чем хочешь заниматься (минимум 5 символов):")
        return
    
    data = await state.get_data()
    
    save_wl_application(
        message.from_user.id,
        message.from_user.username,
        data['name'],
        data['age'],
        data['nickname'],
        data['source'],
        data.get('friend_nick'),
        plans
    )
    
    await send_wl_to_admin(
        message.from_user.id,
        message.from_user.username,
        data['name'],
        data['age'],
        data['nickname'],
        data['source'],
        data.get('friend_nick'),
        plans
    )
    
    await state.clear()
    await message.answer(
        "✅ **Анкета отправлена на рассмотрение!**\n\n"
        "Админ проверит её и ответит в этом чате.\n"
        "Обычно проверка занимает до 24 часов.\n\n"
        "📬 Жди уведомление!",
        reply_markup=get_back_menu()
    )

# ========== ВТОРАЯ ЖИЗНЬ ==========
@dp.callback_query(F.data == "btn_rv")
async def ask_revive_nick(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💀 **ВТОРАЯ ЖИЗНЬ = 30₽** 💀\n\n"
        "1️⃣ Переведи 30₽ на карту:\n"
        "   `2203 8302 2268 9342`\n\n"
        "2️⃣ В сообщении перевода укажи свой никнейм\n\n"
        "3️⃣ Напиши свой ник сюда\n\n"
        "💰 После проверки платежа тебя разбанят!"
    )
    await state.set_state(ReviveForm.waiting_for_nickname)

@dp.message(ReviveForm.waiting_for_nickname)
async def process_revive_nick(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    if not is_valid_nickname(nickname):
        await message.answer("❌ Неверный формат ника! Ник: 3-16 символов, латиница/цифры/_")
        return
    
    if is_already_applied_revive(nickname):
        await message.answer(f"⚠️ Для ника **{nickname}** уже есть активная заявка!")
        await state.clear()
        return
    
    save_revive_application(nickname, message.from_user.id, message.from_user.username)
    await send_revive_to_admin(nickname, message.from_user.id, message.from_user.username)
    await state.clear()
    
    await message.answer(
        f"✅ **Заявка на разбан для {nickname} отправлена!**\n\n"
        f"💰 Админ проверит платёж и разбанит тебя.\n"
        f"⏳ Обычно занимает до 15 минут.",
        reply_markup=get_back_menu()
    )

# ========== ПОМОЩНИК ==========
@dp.callback_query(F.data == "btn_support")
async def support_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🆘 **Помощник**\n\n"
        "Выбери нужный пункт:",
        reply_markup=get_support_menu()
    )

@dp.callback_query(F.data == "btn_faq")
async def faq(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "❓ **Частые вопросы**\n\n"
        "❔ **Как попасть на сервер?**\n"
        "→ Заполни анкету в разделе «Вайт-лист»\n\n"
        "❔ **Что делать если умер?**\n"
        "→ Купи вторую жизнь за 30₽ в разделе «Вторая жизнь»\n\n"
        "❔ **Какая версия Minecraft?**\n"
        "→ 1.21.11\n\n"
        "❔ **Где IP?**\n"
        "→ Выдаётся после одобрения анкеты\n\n"
        "❔ **Почему меня не приняли?**\n"
        "→ Возраст меньше 10 лет или плохая анкета",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "btn_chat_admin")
async def chat_admin(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💬 **Написать админу**\n\n"
        "Напиши своё сообщение. Админ ответит как сможет."
    )
    await state.set_state(SupportForm.waiting_for_message)

@dp.message(SupportForm.waiting_for_message)
async def process_support_message(message: types.Message, state: FSMContext):
    msg_text = message.text.strip()
    
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO admin_chat (user_id, message) VALUES (?, ?)', (message.from_user.id, msg_text))
    conn.commit()
    conn.close()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Ответить", callback_data=f"reply_{message.from_user.id}")
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💌 **Новое сообщение от игрока**\n\n"
             f"👤 @{message.from_user.username or 'нет'} (ID: {message.from_user.id})\n\n"
             f"📝 **Сообщение**:\n{msg_text}",
        reply_markup=kb.as_markup()
    )
    
    await state.clear()
    await message.answer(
        "✅ **Сообщение отправлено!**\n\nАдмин скоро ответит.",
        reply_markup=get_back_menu()
    )

# ========== АДМИН-ОБРАБОТКА ==========
@dp.callback_query(lambda c: c.data.startswith("wl_app_"))
async def approve_wl(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nickname FROM wl_applications WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        nickname = result[0]
        update_wl_status(user_id, 'approved')
        
        server_info = (
            "🎉 **ПОЗДРАВЛЯЮ! ТЫ ПРИНЯТ!** 🎉\n\n"
            "Твоя анкета одобрена!\n\n"
            "📌 **Версия:** 1.21.11\n"
            "🔌 **IP:** `d40.joinserver.xyz:25736`\n\n"
            "💾 Установи мод Simple Voice Chat для голосового чата\n"
            "🔗 Ссылка на мод: https://modrinth.com/plugin/simple-voice-chat\n\n"
            "❤️ Удачи на сервере!"
        )
        
        try:
            await bot.send_message(chat_id=user_id, text=server_info)
            await callback.message.edit_text(f"✅ Анкета `{nickname}` одобрена! Игрок получил IP.")
        except:
            await callback.message.edit_text(f"✅ Одобрен `{nickname}`, но не смог написать ему.")

@dp.callback_query(lambda c: c.data.startswith("wl_deny_"))
async def deny_wl(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    update_wl_status(user_id, 'denied')
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📞 Связаться с разработчиком", url="https://t.me/ahiles_support")
    
    await bot.send_message(
        chat_id=user_id,
        text="❌ **К сожалению, твоя анкета отклонена.**\n\n"
             "Причина: несоответствие требованиям сервера.\n\n"
             "Ты можешь попробовать подать заявку снова через 7 дней.",
        reply_markup=kb.as_markup()
    )
    
    await callback.message.edit_text("❌ Анкета отклонена.")

@dp.callback_query(lambda c: c.data.startswith("rv_app_"))
async def approve_revive(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    data = callback.data.split("_")
    nickname = data[2]
    user_id = int(data[3])
    
    update_revive_status(nickname, 'approved')
    
    server_info = (
        "🎉 **ТЕБЯ РАЗБАНИЛИ!** 🎉\n\n"
        "Ты купил вторую жизнь!\n\n"
        "📌 **Версия:** 1.21.11\n"
        "🔌 **IP:** `d40.joinserver.xyz:25736`\n\n"
        "❤️ Будь осторожнее, жизнь всего одна!"
    )
    
    try:
        await bot.send_message(chat_id=user_id, text=server_info)
        await callback.message.edit_text(f"✅ Разбан для `{nickname}` выполнен!")
    except:
        await callback.message.edit_text(f"✅ Разбан `{nickname}` (не смог написать)")

@dp.callback_query(lambda c: c.data.startswith("rv_deny_"))
async def deny_revive(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    data = callback.data.split("_")
    nickname = data[2]
    user_id = int(data[3])
    
    update_revive_status(nickname, 'denied')
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📞 Связаться с разработчиком", url="https://t.me/ahiles_support")
    
    await bot.send_message(
        chat_id=user_id,
        text=f"❌ **Заявка на разбан для {nickname} отклонена.**\n\n"
             f"Причина: платёж не найден или неправильная сумма.\n\n"
             f"Проверь перевод и попробуй снова.",
        reply_markup=kb.as_markup()
    )
    
    await callback.message.edit_text(f"❌ Разбан для `{nickname}` отклонён.")

@dp.callback_query(lambda c: c.data.startswith("reply_"))
async def reply_to_user(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[1])
    await state.update_data(reply_user_id=user_id)
    
    await callback.message.answer(f"💬 Введи ответ для игрока (ID: {user_id}):")
    await state.set_state("waiting_admin_reply")

@dp.message(lambda msg: msg.from_user.id == ADMIN_ID)
async def process_admin_reply(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state == "waiting_admin_reply":
        data = await state.get_data()
        user_id = data.get('reply_user_id')
        
        if user_id:
            await bot.send_message(
                chat_id=user_id,
                text=f"📬 **Ответ от администратора:**\n\n{message.text}"
            )
            await message.answer("✅ Ответ отправлен игроку!")
            await state.clear()

# ========== ЗАПУСК ==========
async def main():
    print("╔══════════════════════════════════════════╗")
    print("║   🚀 AhilesVanilla Бот Запущен на Render ║")
    print("║   📝 Анкета в Вайт-лист (возраст 10+)   ║")
    print("║   💀 Вторая жизнь за 30₽                ║")
    print("║   🛡️ Защита от дублей: ВКЛ              ║")
    print("╚══════════════════════════════════════════╝")
    
    try:
        me = await bot.get_me()
        print(f"\n✅✅✅ БОТ УСПЕШНО ЗАПУЩЕН! ✅✅✅")
        print(f"📱 Юзернейм бота: @{me.username}")
        print(f"💬 Напиши /start в Telegram боту @{me.username}\n")
        print("🟢 Бот работает...\n")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
        return
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
