import asyncio
import re
import sqlite3
import os
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== ОТКЛЮЧАЕМ ПРОВЕРКУ ПОРТОВ ДЛЯ RENDER ==========
os.environ["RENDER_NO_PORT_CHECK"] = "true"

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
            username TEXT,
            approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_balance (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            code TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            case_type TEXT,
            prize TEXT,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def is_blocked(user_id: int) -> bool:
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def block_user(user_id: int, reason: str = None):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO blocked_users (user_id, reason) VALUES (?, ?)', (user_id, reason))
    conn.commit()
    conn.close()

def unblock_user(user_id: int):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_blocked_users():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, reason, blocked_at FROM blocked_users ORDER BY blocked_at DESC')
    result = cursor.fetchall()
    conn.close()
    return result

def is_already_applied_wl(user_id: int) -> bool:
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM wl_applications WHERE user_id = ? AND status = "pending"', (user_id,))
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

def update_wl_status(user_id, status):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE wl_applications SET status = ? WHERE user_id = ?', (status, user_id))
    if status == 'approved':
        cursor.execute('SELECT nickname, user_name FROM wl_applications WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            cursor.execute('INSERT OR REPLACE INTO approved (user_id, nickname, username) VALUES (?, ?, ?)', 
                          (user_id, result[0], result[1]))
    conn.commit()
    conn.close()

def get_pending_count():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM wl_applications WHERE status = "pending"')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_approved_players():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, nickname, username FROM approved ORDER BY approved_at DESC')
    players = cursor.fetchall()
    conn.close()
    return players

def get_pending_players():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, nickname, user_name FROM wl_applications WHERE status = "pending"')
    players = cursor.fetchall()
    conn.close()
    return players

def get_all_players():
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, nickname FROM wl_applications WHERE status = "approved"')
    players = cursor.fetchall()
    conn.close()
    return players

# ========== ФУНКЦИИ ДЛЯ ВАЛЮТЫ ==========
def get_balance(user_id):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def add_balance(user_id, amount):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_balance (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?', (user_id, amount, amount))
    conn.commit()
    conn.close()

def remove_balance(user_id, amount):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE user_balance SET balance = balance - ? WHERE user_id = ? AND balance >= ?', (amount, user_id, amount))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0

def get_referral_code(user_id):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code FROM referrals WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def create_referral_code(user_id):
    code = f"REF{user_id}{random.randint(1000, 9999)}"
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO referrals (user_id, code) VALUES (?, ?)', (user_id, code))
    conn.commit()
    conn.close()
    return code

def open_case(user_id, case_type):
    # ОБЫЧНЫЙ КЕЙС (25 AHC)
    if case_type == "common":
        r = random.randint(1, 100)
        if r <= 30:
            amount = random.randint(8, 20)
            prize = f"Железо x{amount}"
        elif r <= 50:
            amount = random.randint(16, 32)
            prize = f"Уголь x{amount}"
        elif r <= 65:
            amount = random.randint(4, 10)
            prize = f"Золото x{amount}"
        elif r <= 80:
            amount = random.randint(1, 4)
            prize = f"Алмазы x{amount}"
        elif r <= 90:
            amount = random.randint(1, 3)
            prize = f"Заряды ветра x{amount}"
        elif r <= 97:
            prize = "Зелье регенерации II"
        else:
            prize = "Зелье силы I + Железо x12"
    
    # ЛУТБОКС (50 AHC)
    elif case_type == "epic":
        r = random.randint(1, 100)
        if r <= 25:
            prize = f"Железо x{random.randint(12, 24)} + Золото x{random.randint(3, 8)}"
        elif r <= 45:
            prize = f"Алмазы x{random.randint(2, 6)}"
        elif r <= 60:
            prize = f"Уголь x{random.randint(24, 48)} + Железо x{random.randint(10, 20)}"
        elif r <= 75:
            prize = f"Заряды ветра x{random.randint(2, 5)} + Алмазы x{random.randint(1, 3)}"
        elif r <= 85:
            prize = "Зелье силы II (4:00)"
        elif r <= 93:
            armors = ["Алмазный шлем", "Алмазный нагрудник", "Алмазные поножи", "Алмазные ботинки"]
            prize = random.choice(armors)
        else:
            prize = "Полный сет железной брони"
    
    # ЛЕГЕНДАРНЫЙ КЕЙС (200 AHC)
    else:
        r = random.randint(1, 100)
        if r <= 25:
            prize = f"Алмазы x{random.randint(3, 8)} + Золото x{random.randint(8, 16)}"
        elif r <= 45:
            prize = f"Заряды ветра x{random.randint(3, 7)} + Алмазы x{random.randint(2, 5)} + Золото x{random.randint(10, 20)}"
        elif r <= 65:
            armors = ["Алмазный шлем", "Алмазный нагрудник", "Алмазные поножи", "Алмазные ботинки"]
            item1 = random.choice(armors)
            item2 = random.choice([a for a in armors if a != item1])
            prize = f"{item1} + {item2}"
        elif r <= 80:
            prize = "Алмазная кирка с починкой I"
        elif r <= 92:
            prize = "Налобник с защитой IV"
        else:
            prize = "Полный сет алмазной брони"
    
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cases_history (user_id, case_type, prize) VALUES (?, ?, ?)', (user_id, case_type, prize))
    conn.commit()
    conn.close()
    
    return prize

init_db()

# ========== FSM СОСТОЯНИЯ ==========
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

class AdminStates(StatesGroup):
    waiting_broadcast_message = State()
    waiting_block_user_id = State()
    waiting_unblock_user_id = State()
    waiting_admin_reply = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📜 Правила сервера", callback_data="btn_rules")
    kb.button(text="📝 Подать анкету в Вайт-лист", callback_data="btn_wl")
    kb.button(text="💀 Вторая Жизнь", callback_data="btn_rv")
    kb.button(text="💎 AhilesCoin", callback_data="btn_currency")
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

def get_admin_panel():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="👥 Список игроков", callback_data="admin_players")
    kb.button(text="⏳ Ожидают", callback_data="admin_pending")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="🔒 Заблокировать", callback_data="admin_block")
    kb.button(text="🔓 Разблокировать", callback_data="admin_unblock")
    kb.button(text="🚫 Список заблок", callback_data="admin_blocked_list")
    kb.button(text="💎 Выдать валюту", callback_data="admin_give_currency")
    kb.adjust(1)
    return kb.as_markup()

def get_currency_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Мой баланс", callback_data="my_balance")
    kb.button(text="🎁 Пригласить друга", callback_data="referral")
    kb.button(text="📦 Открыть кейс", callback_data="open_case")
    kb.button(text="💎 Топ игроков", callback_data="top_balance")
    kb.button(text="🔙 Назад", callback_data="btn_menu")
    kb.adjust(1)
    return kb.as_markup()

def get_cases_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Обычный кейс (25 AHC)", callback_data="case_common")
    kb.button(text="🔵 Лутбокс (50 AHC)", callback_data="case_epic")
    kb.button(text="🟣 Легендарный (100 AHC)", callback_data="case_legendary")
    kb.button(text="🔙 Назад", callback_data="btn_currency")
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
    text += f"🎮 **Ник**: `{nickname}`\n"
    text += f"📢 **Откуда узнал**: {source}\n"
    if friend_nick:
        text += f"👥 **Друг**: {friend_nick}\n"
    text += f"🎯 **Чем займётся**: {plans}\n\n"
    text += f"🆔 **ID**: `{user_id}`\n"
    text += f"📊 **В очереди**: {get_pending_count()}"
    
    await bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=kb.as_markup())

# ========== КОМАНДА /START ==========
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ **Вы заблокированы!**")
        return
    
    # Проверка реферальной ссылки
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1].replace("ref_", "")
        conn = sqlite3.connect('whitelist_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM referrals WHERE code = ?', (ref_code,))
        result = cursor.fetchone()
        conn.close()
        if result and result[0] != message.from_user.id:
            referrer_id = result[0]
            # Сохраняем реферера (потом при одобрении заявки дадим бонус)
            conn = sqlite3.connect('whitelist_bot.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE referrals SET referrer_id = ? WHERE user_id = ?', (referrer_id, message.from_user.id))
            conn.commit()
            conn.close()
            await message.answer("🎁 Ты перешел по реферальной ссылке! Если пройдешь вайт-лист - твой друг получит бонус!")
    
    await state.clear()
    await message.answer(
        "✨ **Добро пожаловать на AhilesVanilla!** ✨\n\n"
        "🎮 Хардкорный сервер с одной жизнью\n"
        "🎙️ Голосовой чат\n\n"
        "👇 Выбери действие:",
        reply_markup=get_main_menu()
    )

# ========== НАВИГАЦИЯ ==========
@dp.callback_query(F.data == "btn_menu")
async def go_menu(callback: types.CallbackQuery, state: FSMContext):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("✨ Главное меню:", reply_markup=get_main_menu())

@dp.callback_query(F.data == "btn_about")
async def show_about(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "ℹ️ **О проекте**\n\n"
        "🎮 Хардкор (1 жизнь)\n"
        "🎙️ Голосовой чат\n"
        "💰 2 жизнь = 30₽ или 200 AHC\n"
        "💎 AhilesCoin - внутренняя валюта\n"
        "⚔️ Булава: макс. 2 шт., чары запрещены",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "btn_rules")
async def show_rules(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "📜 **ПРАВИЛА**\n\n"
        "1️⃣ Без читов!\n"
        "2️⃣ Смерть = бан (2 жизнь 30₽ или 200 AHC)\n"
        "3️⃣ Булава: макс. 2 шт., чары запрещены\n"
        "4️⃣ Без гриферства",
        reply_markup=get_back_menu()
    )

# ========== ВАЙТ-ЛИСТ ==========
@dp.callback_query(F.data == "btn_wl")
async def start_wl(callback: types.CallbackQuery, state: FSMContext):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    if is_already_applied_wl(callback.from_user.id):
        await callback.answer("⚠️ У тебя уже есть активная заявка!", show_alert=True)
        return
    await callback.message.edit_text("📝 **Анкета в Вайт-лист**\n\nНапиши своё **имя**:")
    await state.set_state(WLForm.waiting_for_name)

@dp.message(StateFilter(WLForm.waiting_for_name))
async def process_name(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    if len(message.text) < 2:
        await message.answer("❌ Слишком короткое имя! Напиши нормально:")
        return
    await state.update_data(name=message.text.strip())
    await message.answer("📅 Напиши свой **возраст** (только число):")
    await state.set_state(WLForm.waiting_for_age)

@dp.message(StateFilter(WLForm.waiting_for_age))
async def process_age(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    try:
        age = int(message.text.strip())
        if age < 10:
            await message.answer("❌ Сервер 10+! Ты не проходишь по возрасту.")
            await state.clear()
            return
        await state.update_data(age=age)
        await message.answer("🎮 Напиши свой **Minecraft ник** (латиница, цифры, _):")
        await state.set_state(WLForm.waiting_for_nickname)
    except ValueError:
        await message.answer("❌ Напиши число!")

@dp.message(StateFilter(WLForm.waiting_for_nickname))
async def process_wl_nickname(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    nickname = message.text.strip()
    if not is_valid_nickname(nickname):
        await message.answer("❌ Неверный формат! Ник: 3-16 символов, латиница/цифры/_")
        return
    await state.update_data(nickname=nickname)
    await message.answer("📢 Откуда узнал о сервере? (TikTok, YouTube, от друга, реклама)")
    await state.set_state(WLForm.waiting_for_source)

@dp.message(StateFilter(WLForm.waiting_for_source))
async def process_source(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    source = message.text.strip()
    await state.update_data(source=source)
    
    if "друг" in source.lower():
        await message.answer("👥 Напиши ник друга, который тебя пригласил:")
        await state.set_state(WLForm.waiting_for_friend_nick)
    else:
        await state.update_data(friend_nick=None)
        await message.answer("🎯 Чем планируешь заниматься на сервере?")
        await state.set_state(WLForm.waiting_for_plans)

@dp.message(StateFilter(WLForm.waiting_for_friend_nick))
async def process_friend(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    await state.update_data(friend_nick=message.text.strip())
    await message.answer("🎯 Чем планируешь заниматься на сервере?")
    await state.set_state(WLForm.waiting_for_plans)

@dp.message(StateFilter(WLForm.waiting_for_plans))
async def process_plans(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    plans = message.text.strip()
    if len(plans) < 5:
        await message.answer("❌ Напиши подробнее (минимум 5 символов):")
        return
    
    data = await state.get_data()
    save_wl_application(
        message.from_user.id, message.from_user.username,
        data['name'], data['age'], data['nickname'],
        data['source'], data.get('friend_nick'), plans
    )
    
    # Награда за реферала
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT referrer_id FROM referrals WHERE user_id = ?', (message.from_user.id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0]:
        add_balance(result[0], 50)
        await bot.send_message(result[0], f"🎉 Твой друг {message.from_user.username} подал заявку! +50 AhilesCoin")
    
    await send_wl_to_admin(
        message.from_user.id, message.from_user.username,
        data['name'], data['age'], data['nickname'],
        data['source'], data.get('friend_nick'), plans
    )
    await state.clear()
    await message.answer("✅ **Анкета отправлена!** Админ скоро ответит.", reply_markup=get_back_menu())

# ========== ВТОРАЯ ЖИЗНЬ ==========
@dp.callback_query(F.data == "btn_rv")
async def ask_revive_pay_method(callback: types.CallbackQuery, state: FSMContext):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 За деньги (30₽)", callback_data="revive_money")
    kb.button(text="💎 За валюту (200 AHC)", callback_data="revive_currency")
    kb.button(text="🔙 Назад", callback_data="btn_menu")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "💀 **ВТОРАЯ ЖИЗНЬ**\n\n"
        "Выбери способ оплаты:\n\n"
        "• Деньги: 30₽\n"
        "• Валюта: 200 AhilesCoin",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "revive_money")
async def revive_money(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💀 **Оплата за деньги**\n\n"
        "1️⃣ Переведи 30₽ на карту: `2203 8302 2268 9342`\n"
        "2️⃣ Напиши свой ник в чат"
    )
    await state.update_data(pay_method="money")
    await state.set_state(ReviveForm.waiting_for_nickname)

@dp.callback_query(F.data == "revive_currency")
async def revive_currency(callback: types.CallbackQuery, state: FSMContext):
    balance = get_balance(callback.from_user.id)
    if balance < 200:
        await callback.answer(f"❌ Не хватает! У тебя {balance} AHC, нужно 200", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💀 **Оплата валютой**\n\n"
        "Напиши свой ник в чат"
    )
    await state.update_data(pay_method="currency")
    await state.set_state(ReviveForm.waiting_for_nickname)

@dp.message(StateFilter(ReviveForm.waiting_for_nickname))
async def process_revive_nick_with_pay(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    
    nickname = message.text.strip()
    if not is_valid_nickname(nickname):
        await message.answer("❌ Неверный формат ника!")
        return
    
    data = await state.get_data()
    pay_method = data.get("pay_method", "money")
    
    if pay_method == "currency":
        balance = get_balance(message.from_user.id)
        if balance < 200:
            await message.answer(f"❌ Не хватает AHC! Нужно 200, у тебя {balance}")
            await state.clear()
            return
        remove_balance(message.from_user.id, 200)
        
        await message.answer(
            f"✅ **Разбан для {nickname} выполнен!**\n\n"
            f"🔌 IP: `d40.joinserver.xyz:25736`\n"
            f"📌 Версия: 1.21.11\n\n"
            f"💰 Остаток AHC: {get_balance(message.from_user.id)}"
        )
        
        await bot.send_message(
            ADMIN_ID,
            f"💎 **Разбан за валюту!**\n\n"
            f"👤 @{message.from_user.username or 'нет'} (ID: {message.from_user.id})\n"
            f"🎮 Ник: `{nickname}`\n"
            f"💰 Потрачено: 200 AHC"
        )
    else:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Одобрить", callback_data=f"rv_app_{nickname}_{message.from_user.id}")
        kb.button(text="❌ Отклонить", callback_data=f"rv_deny_{nickname}_{message.from_user.id}")
        
        await bot.send_message(
            ADMIN_ID,
            f"🔔 **ЗАЯВКА НА РАЗБАН (деньги)**\n\n"
            f"🎮 Ник: `{nickname}`\n"
            f"👤 @{message.from_user.username or 'нет'} (ID: {message.from_user.id})\n"
            f"💰 Проверь карту `2203 8302 2268 9342`",
            reply_markup=kb.as_markup()
        )
        await message.answer(f"✅ Заявка на разбан для {nickname} отправлена!", reply_markup=get_back_menu())
    
    await state.clear()

# ========== ВАЛЮТА И КЕЙСЫ ==========
@dp.callback_query(F.data == "btn_currency")
async def currency_menu(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "💎 **AhilesCoin — твоя валюта!**\n\n"
        "💰 Зарабатывай: приглашай друзей (50 AHC)\n"
        "🎁 Трать: открывай кейсы, покупай разбан (200 AHC)\n\n"
        "👇 Выбери действие:",
        reply_markup=get_currency_menu()
    )

@dp.callback_query(F.data == "my_balance")
async def show_balance(callback: types.CallbackQuery):
    balance = get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"💰 **Твой баланс:** `{balance} AhilesCoin`\n\n"
        f"💡 **Как заработать:**\n"
        f"• Пригласи друга (по твоей ссылке) — +50 AHC\n"
        f"• Друг купил разбан за деньги — +25 AHC\n"
        f"• Друг купил разбан за валюту — +10 AHC\n\n"
        f"🎁 Разбан стоит 200 AHC",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "referral")
async def show_referral(callback: types.CallbackQuery):
    code = get_referral_code(callback.from_user.id)
    if not code:
        code = create_referral_code(callback.from_user.id)
    
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{code}"
    
    await callback.message.edit_text(
        f"🎁 **Пригласи друга!**\n\n"
        f"🔗 Твоя ссылка:\n`{ref_link}`\n\n"
        f"🏆 **Награда:**\n"
        f"• Друг подал анкету — +50 AHC\n"
        f"• Друг купил разбан за деньги — +25 AHC\n"
        f"• Друг купил разбан за валюту — +10 AHC\n\n"
        f"💎 У тебя уже есть реферальный код!",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "open_case")
async def cases_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📦 **Выбери кейс:**\n\n"
        "🟢 Обычный (25 AHC) — ресурсы\n"
        "🔵 Лутбокс (50 AHC) — ресурсы + броня\n"
        "🟣 Легендарный (100 AHC) — алмазы + зачарованные вещи",
        reply_markup=get_cases_menu()
    )

@dp.callback_query(F.data == "btn_currency")
async def back_to_currency(callback: types.CallbackQuery):
    await currency_menu(callback)

@dp.callback_query(lambda c: c.data.startswith("case_"))
async def open_case_handler(callback: types.CallbackQuery):
    case_type = callback.data.split("_")[1]
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    prices = {"common": 25, "epic": 50, "legendary": 100}
    price = prices.get(case_type, 25)
    names = {"common": "Обычный", "epic": "Лутбокс", "legendary": "Легендарный"}
    
    if balance < price:
        await callback.answer(f"❌ Не хватает! Нужно {price} AHC", show_alert=True)
        return
    
    remove_balance(user_id, price)
    prize = open_case(user_id, case_type)
    
    await callback.message.edit_text(
        f"🎲 **Ты открыл {names[case_type]} кейс!**\n\n"
        f"🏆 Тебе выпало:\n**{prize}**\n\n"
        f"💰 Остаток: {get_balance(user_id)} AHC",
        reply_markup=get_cases_menu()
    )
    
    await bot.send_message(
        ADMIN_ID,
        f"🎁 **Игрок открыл кейс!**\n\n"
        f"👤 @{callback.from_user.username or 'нет'} (ID: {user_id})\n"
        f"📦 Кейс: {names[case_type]}\n"
        f"🏆 Выпало: {prize}"
    )

@dp.callback_query(F.data == "top_balance")
async def top_balance(callback: types.CallbackQuery):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.user_id, u.balance, COALESCE(w.nickname, 'Неизвестно') 
        FROM user_balance u
        LEFT JOIN wl_applications w ON u.user_id = w.user_id AND w.status = 'approved'
        ORDER BY u.balance DESC LIMIT 10
    ''')
    top = cursor.fetchall()
    conn.close()
    
    if not top:
        await callback.message.edit_text("📭 Топ пуст.", reply_markup=get_back_menu())
        return
    
    text = "🏆 **ТОП ПО AhilesCoin** 🏆\n\n"
    for i, (uid, bal, nick) in enumerate(top, 1):
        text += f"{i}. `{nick or uid}` — {bal} AHC\n"
    
    await callback.message.edit_text(text, reply_markup=get_back_menu())

# ========== ПОМОЩНИК ==========
@dp.callback_query(F.data == "btn_support")
async def support_menu(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text("🆘 **Помощник**", reply_markup=get_support_menu())

@dp.callback_query(F.data == "btn_faq")
async def faq(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "❓ **FAQ**\n\n"
        "• Как попасть? → Анкета\n"
        "• Умер? → 2 жизнь 30₽ или 200 AHC\n"
        "• Как заработать AHC? → Приглашай друзей\n"
        "• Версия: 1.21.11",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "btn_chat_admin")
async def chat_admin(callback: types.CallbackQuery, state: FSMContext):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text("💬 Напиши сообщение админу:")
    await state.set_state(SupportForm.waiting_for_message)

@dp.message(StateFilter(SupportForm.waiting_for_message))
async def process_support_message(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы!")
        await state.clear()
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Ответить", callback_data=f"reply_{message.from_user.id}")
    await bot.send_message(ADMIN_ID, f"💌 **Сообщение от игрока**\n\n@{message.from_user.username or 'нет'} (ID: {message.from_user.id})\n\n{message.text}", reply_markup=kb.as_markup())
    await state.clear()
    await message.answer("✅ Сообщение отправлено!", reply_markup=get_back_menu())

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(lambda msg: msg.text == "/admin" and msg.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("👑 **АДМИН-ПАНЕЛЬ**\n\nВыбери действие:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    approved = len(get_approved_players())
    pending = get_pending_count()
    blocked = len(get_blocked_users())
    await callback.message.edit_text(f"📊 **СТАТИСТИКА**\n\n✅ Принято: {approved}\n⏳ Ожидают: {pending}\n🚫 Заблокировано: {blocked}", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_players")
async def admin_players(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    players = get_approved_players()
    if not players:
        await callback.message.edit_text("📭 Нет игроков.", reply_markup=get_admin_panel())
        return
    text = "👥 **ИГРОКИ**\n\n"
    for user_id, nickname, username in players[:20]:
        text += f"• {nickname} — @{username or 'нет'} (ID: {user_id})\n"
    await callback.message.edit_text(text, reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_pending")
async def admin_pending(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    pending = get_pending_players()
    if not pending:
        await callback.message.edit_text("📭 Нет заявок.", reply_markup=get_admin_panel())
        return
    text = "⏳ **ОЖИДАЮТ**\n\n"
    for user_id, nickname, user_name in pending[:20]:
        text += f"• {nickname} — @{user_name or 'нет'} (ID: {user_id})\n"
    await callback.message.edit_text(text, reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_blocked_list")
async def admin_blocked_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    blocked = get_blocked_users()
    if not blocked:
        await callback.message.edit_text("🚫 Нет заблокированных.", reply_markup=get_admin_panel())
        return
    text = "🚫 **ЗАБЛОКИРОВАНЫ**\n\n"
    for user_id, reason, blocked_at in blocked[:20]:
        text += f"• ID: {user_id}\n  Причина: {reason}\n\n"
    await callback.message.edit_text(text, reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_block")
async def admin_block(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text("🔒 Введи ID игрока и причину через пробел:\nПример: `8935740667 Спам`")
    await state.set_state(AdminStates.waiting_block_user_id)

@dp.message(StateFilter(AdminStates.waiting_block_user_id))
async def process_block_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.strip().split(' ', 1)
    user_id = int(parts[0])
    reason = parts[1] if len(parts) > 1 else "Не указана"
    if user_id == ADMIN_ID:
        await message.answer("❌ Нельзя заблокировать себя!")
        await state.clear()
        return
    block_user(user_id, reason)
    await message.answer(f"✅ Игрок {user_id} заблокирован!")
    try:
        await bot.send_message(user_id, f"❌ **Вы заблокированы!**\nПричина: {reason}")
    except:
        pass
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_unblock")
async def admin_unblock(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text("🔓 Введи ID игрока для разблокировки:")
    await state.set_state(AdminStates.waiting_unblock_user_id)

@dp.message(StateFilter(AdminStates.waiting_unblock_user_id))
async def process_unblock_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    user_id = int(message.text.strip())
    unblock_user(user_id)
    await message.answer(f"✅ Игрок {user_id} разблокирован!")
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text("📢 Введи текст рассылки:")
    await state.set_state(AdminStates.waiting_broadcast_message)

@dp.message(StateFilter(AdminStates.waiting_broadcast_message))
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    players = get_all_players()
    sent = 0
    for user_id, nickname in players:
        try:
            await bot.send_message(user_id, f"📢 **РАССЫЛКА ОТ АДМИНА**\n\n{message.text}")
            sent += 1
        except:
            pass
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Отправлено: {sent} игрокам")
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_give_currency")
async def admin_give_currency(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text("💎 Введи ID игрока и сумму:\nПример: `8935740667 100`")
    await state.set_state("waiting_give_currency")

@dp.message(lambda msg: msg.from_user.id == ADMIN_ID)
async def process_give_currency(message: types.Message, state: FSMContext):
    if await state.get_state() == "waiting_give_currency":
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.answer("❌ Формат: `ID Сумма`")
            return
        try:
            user_id = int(parts[0])
            amount = int(parts[1])
            add_balance(user_id, amount)
            await message.answer(f"✅ Выдано {amount} AHC игроку {user_id}")
            await bot.send_message(user_id, f"🎁 Админ выдал тебе {amount} AhilesCoin!")
        except:
            await message.answer("❌ Ошибка! Пример: `8935740667 100`")
        await state.clear()

# ========== ОБРАБОТКА РЕШЕНИЙ АДМИНА ==========
@dp.callback_query(lambda c: c.data.startswith("wl_app_"))
async def approve_wl(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    user_id = int(callback.data.split("_")[2])
    update_wl_status(user_id, 'approved')
    
    # Награда за реферала при успешном прохождении вайт-листа
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT referrer_id FROM referrals WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0]:
        add_balance(result[0], 50)
        await bot.send_message(result[0], f"🎉 Твой друг прошёл вайт-лист! +50 AhilesCoin")
    
    await bot.send_message(user_id, "🎉 **ПОЗДРАВЛЯЮ! ТЫ ПРИНЯТ!**\n\n📌 Версия: 1.21.11\n🔌 IP: `d40.joinserver.xyz:25736`")
    await callback.message.edit_text("✅ Игрок одобрен!")

@dp.callback_query(lambda c: c.data.startswith("wl_deny_"))
async def deny_wl(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    user_id = int(callback.data.split("_")[2])
    update_wl_status(user_id, 'denied')
    await bot.send_message(user_id, "❌ Анкета отклонена.")
    await callback.message.edit_text("❌ Отклонено.")

@dp.callback_query(lambda c: c.data.startswith("rv_app_"))
async def approve_revive(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    data = callback.data.split("_")
    nickname = data[2]
    user_id = int(data[3])
    await bot.send_message(user_id, f"🎉 **ТЕБЯ РАЗБАНИЛИ!**\n\n🔌 IP: `d40.joinserver.xyz:25736`")
    await callback.message.edit_text(f"✅ Разбан для {nickname} выполнен!")

@dp.callback_query(lambda c: c.data.startswith("rv_deny_"))
async def deny_revive(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    data = callback.data.split("_")
    nickname = data[2]
    user_id = int(data[3])
    await bot.send_message(user_id, "❌ Заявка на разбан отклонена. Платёж не найден.")
    await callback.message.edit_text(f"❌ Отклонено.")

@dp.callback_query(lambda c: c.data.startswith("reply_"))
async def reply_to_user(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    user_id = int(callback.data.split("_")[1])
    await state.update_data(reply_user_id=user_id)
    await callback.message.answer(f"💬 Введи ответ для игрока:")
    await state.set_state(AdminStates.waiting_admin_reply)

@dp.message(StateFilter(AdminStates.waiting_admin_reply))
async def process_admin_reply(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    user_id = data.get('reply_user_id')
    if user_id:
        await bot.send_message(user_id, f"📬 **Ответ админа:**\n\n{message.text}")
        await message.answer("✅ Ответ отправлен!")
    await state.clear()

# ========== ЗАПУСК ==========
async def main():
    print("╔══════════════════════════════════════════╗")
    print("║   🚀 AhilesVanilla Бот Запущен          ║")
    print("║   💎 AhilesCoin - кейсы и разбан        ║")
    print("║   👑 Админ-панель: /admin               ║")
    print("╚══════════════════════════════════════════╝")
    try:
        me = await bot.get_me()
        print(f"\n✅ Бот @{me.username} запущен!")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        return
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
