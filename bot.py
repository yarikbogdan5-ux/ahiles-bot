import asyncio
import re
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os

# ========== КОНФИГ ==========
TOKEN = "8875140720:AAH3qzwBAJ7E7rpl9Zs0tuinSXzYdp-hl5Q"
ADMIN_ID = 8935740667

# Настройки рекламы
ADVERTISEMENT_ENABLED = True
ADVERTISEMENT_INTERVAL_HOURS = 1
ADVERTISEMENT_TEXT = (
    "📢 **РЕКЛАМА НА СЕРВЕРЕ!** 📢\n\n"
    "🎮 Хочешь разместить свою рекламу?\n"
    "💰 Цена: 50 рублей / час\n"
    "📞 По вопросам: @ahiles_support"
)

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
        CREATE TABLE IF NOT EXISTS admin_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            reply TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_settings (
            id INTEGER PRIMARY KEY,
            enabled BOOLEAN DEFAULT 1,
            interval_hours INTEGER DEFAULT 1,
            last_sent TIMESTAMP
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO ad_settings (id, enabled, interval_hours) VALUES (1, 1, 1)')
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

# Остальные функции из предыдущего кода...
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

def save_admin_reply(user_id, message, reply):
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO admin_chat (user_id, message, reply) VALUES (?, ?, ?)', (user_id, message, reply))
    conn.commit()
    conn.close()

init_db()

# ========== FSM СОСТОЯНИЯ ==========
class WLForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_nickname = State()
    waiting_for_source = State()
    waiting_for_friend_nick = State()
    waiting_for_plans = State()

class AdminStates(StatesGroup):
    waiting_broadcast_message = State()
    waiting_block_user_id = State()
    waiting_unblock_user_id = State()

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

def get_admin_panel():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="👥 Список игроков", callback_data="admin_players")
    kb.button(text="⏳ Ожидают", callback_data="admin_pending")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="🔒 Заблокировать игрока", callback_data="admin_block")
    kb.button(text="🔓 Разблокировать", callback_data="admin_unblock")
    kb.button(text="🚫 Список заблок", callback_data="admin_blocked_list")
    kb.button(text="🔄 Перезагрузить", callback_data="admin_reload")
    kb.adjust(1)
    return kb.as_markup()

def is_valid_nickname(nick):
    return bool(re.match(r"^[a-zA-Z0-9_]{3,16}$", nick))

# ========== АДМИН-ОТПРАВКА ==========
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

# ========== КОМАНДА /START ==========
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("❌ **Вы заблокированы!**\n\nВы не можете использовать бота.")
        return
    
    await state.clear()
    await message.answer(
        "✨ **Добро пожаловать на AhilesVanilla!** ✨\n\n"
        "🎮 Хардкорный сервер с одной жизнью\n"
        "🎙️ Голосовой чат\n\n"
        "📝 **Чтобы попасть на сервер - заполни анкету!**\n\n"
        "👇 Выбери действие:",
        reply_markup=get_main_menu()
    )

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(lambda msg: msg.text == "/admin" and msg.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer(
        "👑 **АДМИН-ПАНЕЛЬ**\n\n"
        f"📊 Заявок в очереди: {get_pending_count()}\n"
        f"✅ Принято игроков: {len(get_approved_players())}\n\n"
        "Выбери действие:",
        reply_markup=get_admin_panel()
    )

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    approved = len(get_approved_players())
    pending = get_pending_count()
    blocked = len(get_blocked_users())
    
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n"
        f"✅ Принято игроков: {approved}\n"
        f"⏳ Ожидают: {pending}\n"
        f"🚫 Заблокировано: {blocked}\n\n"
        f"🕒 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        reply_markup=get_admin_panel()
    )

@dp.callback_query(F.data == "admin_players")
async def admin_players(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    players = get_approved_players()
    if not players:
        await callback.message.edit_text("📭 Нет принятых игроков.", reply_markup=get_admin_panel())
        return
    
    text = "👥 **СПИСОК ИГРОКОВ**\n\n"
    for user_id, nickname, username in players[:20]:
        text += f"• `{nickname}` — @{username or 'нет'} (ID: `{user_id}`)\n"
    
    if len(players) > 20:
        text += f"\n... и ещё {len(players) - 20} игроков"
    
    await callback.message.edit_text(text, reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_pending")
async def admin_pending(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    conn = sqlite3.connect('whitelist_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, nickname, user_name, created_at FROM wl_applications WHERE status = "pending"')
    pending = cursor.fetchall()
    conn.close()
    
    if not pending:
        await callback.message.edit_text("📭 Нет ожидающих заявок.", reply_markup=get_admin_panel())
        return
    
    text = "⏳ **ОЖИДАЮТ РАССМОТРЕНИЯ**\n\n"
    for user_id, nickname, user_name, created_at in pending[:20]:
        text += f"• `{nickname}` — @{user_name or 'нет'} (ID: `{user_id}`)\n"
    
    if len(pending) > 20:
        text += f"\n... и ещё {len(pending) - 20} заявок"
    
    await callback.message.edit_text(text, reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_block")
async def admin_block(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🚫 **Заблокировать игрока**\n\n"
        "Введи ID игрока (число) и причину через пробел.\n"
        "Пример: `8935740667 Спам и оскорбления`\n\n"
        "Или отправь только ID, без причины."
    )
    await state.set_state(AdminStates.waiting_block_user_id)

@dp.message(AdminStates.waiting_block_user_id)
async def process_block_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    parts = message.text.strip().split(' ', 1)
    user_id = int(parts[0])
    reason = parts[1] if len(parts) > 1 else "Не указана"
    
    if user_id == ADMIN_ID:
        await message.answer("❌ Нельзя заблокировать самого себя!")
        await state.clear()
        return
    
    block_user(user_id, reason)
    await message.answer(f"✅ Игрок `{user_id}` заблокирован!\nПричина: {reason}")
    
    try:
        await bot.send_message(user_id, f"❌ **Вы заблокированы в боте!**\n\nПричина: {reason}\n\nЕсли считаете ошибкой - @ahiles_support")
    except:
        pass
    
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_unblock")
async def admin_unblock(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔓 **Разблокировать игрока**\n\n"
        "Введи ID игрока для разблокировки:\n"
        "Пример: `8935740667`"
    )
    await state.set_state(AdminStates.waiting_unblock_user_id)

@dp.message(AdminStates.waiting_unblock_user_id)
async def process_unblock_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_id = int(message.text.strip())
    unblock_user(user_id)
    await message.answer(f"✅ Игрок `{user_id}` разблокирован!")
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_blocked_list")
async def admin_blocked_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    blocked = get_blocked_users()
    if not blocked:
        await callback.message.edit_text("🚫 Нет заблокированных игроков.", reply_markup=get_admin_panel())
        return
    
    text = "🚫 **ЗАБЛОКИРОВАННЫЕ ИГРОКИ**\n\n"
    for user_id, reason, blocked_at in blocked[:20]:
        text += f"• ID: `{user_id}`\n"
        text += f"  Причина: {reason}\n"
        text += f"  Дата: {blocked_at[:16]}\n\n"
    
    await callback.message.edit_text(text, reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 **РАССЫЛКА**\n\n"
        "Введи текст сообщения для рассылки ВСЕМ игрокам.\n\n"
        "Для отмены отправь /cancel"
    )
    await state.set_state(AdminStates.waiting_broadcast_message)

@dp.message(AdminStates.waiting_broadcast_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.text == "/cancel":
        await message.answer("❌ Рассылка отменена.")
        await state.clear()
        return
    
    players = get_all_players()
    if not players:
        await message.answer("📭 Нет игроков для рассылки.")
        await state.clear()
        return
    
    sent = 0
    failed = 0
    
    for user_id, nickname in players:
        try:
            await bot.send_message(user_id, f"📢 **РАССЫЛКА ОТ АДМИНА**\n\n{message.text}")
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await message.answer(f"✅ Рассылка завершена!\n📨 Отправлено: {sent}\n❌ Не доставлено: {failed}")
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "admin_reload")
async def admin_reload(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text("🔄 Перезагрузка админ-панели...", reply_markup=get_admin_panel())

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
        "ℹ️ **О проекте AhilesVanilla**\n\n"
        "🎮 Режим: Хардкор (1 жизнь)\n"
        "🎙️ Голосовой чат: Simple Voice Chat\n"
        "🛡️ Защита: Grim Anticheat + Anti-Xray\n"
        "💰 Вторая жизнь: 30₽\n"
        "⚔️ Булава: макс. 2 шт., чары запрещены\n"
        "👑 Админ: Ahiles\n\n"
        "💬 По вопросам: @ahiles_support",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "btn_rules")
async def show_rules(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "📜 **ПРАВИЛА СЕРВЕРА**\n\n"
        "1️⃣ Без читов! → Вечный бан\n"
        "2️⃣ Смерть = бан (купи 2 жизнь за 30₽)\n"
        "3️⃣ **Оружие - Булава**\n"
        "   → Максимум 2 булавы на игрока\n"
        "   → Чары на булаву ЗАПРЕЩЕНЫ\n"
        "4️⃣ Без гриферства\n"
        "5️⃣ Уважай других игроков\n\n"
        "✨ Приятной игры!",
        reply_markup=get_back_menu()
    )

# ========== ВАЙТ-ЛИСТ (АНКЕТА) - с проверкой блокировки ==========
@dp.callback_query(F.data == "btn_wl")
async def start_wl(callback: types.CallbackQuery, state: FSMContext):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    
    if is_already_applied_wl(callback.from_user.id):
        await callback.answer("⚠️ У тебя уже есть активная заявка!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 **Анкета в Вайт-лист**\n\n"
        "Для начала напиши своё **настоящее имя**:"
    )
    await state.set_state(WLForm.waiting_for_name)

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ АНКЕТЫ (те же, что были) ==========
@dp.message(WLForm.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
    if len(message.text) < 2:
        await message.answer("❌ Слишком короткое имя! Напиши нормально:")
        return
    await state.update_data(name=message.text.strip())
    await message.answer("📅 Теперь напиши свой **возраст** (только число):")
    await state.set_state(WLForm.waiting_for_age)

@dp.message(WLForm.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
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
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
    nickname = message.text.strip()
    if not is_valid_nickname(nickname):
        await message.answer("❌ Неверный формат! Ник: 3-16 символов, латиница/цифры/_")
        return
    await state.update_data(nickname=nickname)
    await message.answer("📢 Откуда ты узнал о сервере?\n\nВарианты: TikTok, YouTube, от друга, реклама, другое")
    await state.set_state(WLForm.waiting_for_source)

@dp.message(WLForm.waiting_for_source)
async def process_source(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
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
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
    await state.update_data(friend_nick=message.text.strip())
    await message.answer("🎯 Чем ты планируешь заниматься на сервере?\n\n(строительство, пвп, фермы, исследования и т.д.)")
    await state.set_state(WLForm.waiting_for_plans)

@dp.message(WLForm.waiting_for_plans)
async def process_plans(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
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
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "💀 **ВТОРАЯ ЖИЗНЬ = 30₽** 💀\n\n"
        "1️⃣ Переведи 30₽ на карту:\n"
        "   `2203 8302 2268 9342`\n\n"
        "2️⃣ В сообщении перевода укажи свой никнейм\n\n"
        "3️⃣ Напиши свой ник сюда\n\n"
        "💰 После проверки платежа тебя разбанят!"
    )
    await state.set_state("waiting_revive_nick")

@dp.message(lambda msg: msg.state == "waiting_revive_nick")
async def process_revive_nick(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
    nickname = message.text.strip()
    if not is_valid_nickname(nickname):
        await message.answer("❌ Неверный формат ника! Ник: 3-16 символов, латиница/цифры/_")
        return
    
    from datetime import datetime
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"rv_app_{nickname}_{message.from_user.id}")
    kb.button(text="❌ Отклонить", callback_data=f"rv_deny_{nickname}_{message.from_user.id}")
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 **ЗАЯВКА НА РАЗБАН**\n\n"
             f"🎮 Ник: `{nickname}`\n"
             f"🆔 ID: `{message.from_user.id}`\n"
             f"💰 Проверь карту",
        reply_markup=kb.as_markup()
    )
    
    await state.clear()
    await message.answer(
        f"✅ Заявка на разбан для {nickname} отправлена!\n"
        f"Админ проверит платёж и ответит.",
        reply_markup=get_back_menu()
    )

# ========== ПОМОЩНИК ==========
@dp.callback_query(F.data == "btn_support")
async def support_menu(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "🆘 **Помощник**\n\nВыбери пункт:",
        reply_markup=get_support_menu()
    )

@dp.callback_query(F.data == "btn_faq")
async def faq(callback: types.CallbackQuery):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "❓ **ЧАСТЫЕ ВОПРОСЫ**\n\n"
        "❔ Как попасть? → Анкета в разделе Вайт-лист\n"
        "❔ Умер? → Купи вторую жизнь за 30₽\n"
        "❔ Версия? → 1.21.11\n"
        "❔ IP? → Выдаётся после одобрения\n"
        "❔ Сколько булав? → Максимум 2\n"
        "❔ Чары на булаву? → Запрещены",
        reply_markup=get_back_menu()
    )

@dp.callback_query(F.data == "btn_chat_admin")
async def chat_admin(callback: types.CallbackQuery, state: FSMContext):
    if is_blocked(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    await callback.message.edit_text(
        "💬 **НАПИСАТЬ АДМИНУ**\n\n"
        "Напиши своё сообщение. Админ ответит в этот чат."
    )
    await state.set_state("waiting_admin_message")

@dp.message(lambda msg: msg.state == "waiting_admin_message")
async def process_admin_message(message: types.Message, state: FSMContext):
    if is_blocked(message.from_user.id):
        await message.answer("⛔ Вы заблокированы!")
        return
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Ответить", callback_data=f"reply_{message.from_user.id}")
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💌 **Сообщение от игрока**\n\n"
             f"👤 @{message.from_user.username or 'нет'} (ID: {message.from_user.id})\n\n"
             f"📝 {message.text}",
        reply_markup=kb.as_markup()
    )
    
    await state.clear()
    await message.answer("✅ Сообщение отправлено!", reply_markup=get_back_menu())

# ========== ОБРАБОТКА РЕШЕНИЙ АДМИНА ==========
@dp.callback_query(lambda c: c.data.startswith("wl_app_"))
async def approve_wl(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    update_wl_status(user_id, 'approved')
    
    server_info = (
        "🎉 **ПОЗДРАВЛЯЮ! ТЫ ПРИНЯТ!** 🎉\n\n"
        "Твоя анкета одобрена!\n\n"
        "📌 **Версия:** 1.21.11\n"
        "🔌 **IP:** `d40.joinserver.xyz:25736`\n\n"
        "⚔️ **Правила булавы:** макс. 2 шт., чары запрещены\n\n"
        "❤️ Удачи на сервере!"
    )
    
    try:
        await bot.send_message(chat_id=user_id, text=server_info)
        await callback.message.edit_text(f"✅ Игрок одобрен!")
    except:
        await callback.message.edit_text(f"✅ Одобрен, но не смог написать.")

@dp.callback_query(lambda c: c.data.startswith("wl_deny_"))
async def deny_wl(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    update_wl_status(user_id, 'denied')
    
    await bot.send_message(
        chat_id=user_id,
        text="❌ **Анкета отклонена.**\n\nПричина: несоответствие требованиям."
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
    
    await bot.send_message(
        chat_id=user_id,
        text=f"🎉 **ТЕБЯ РАЗБАНИЛИ!** 🎉\n\n"
             f"Ты купил вторую жизнь!\n"
             f"📌 Версия: 1.21.11\n"
             f"🔌 IP: `d40.joinserver.xyz:25736`"
    )
    await callback.message.edit_text(f"✅ Разбан для {nickname} выполнен!")

@dp.callback_query(lambda c: c.data.startswith("rv_deny_"))
async def deny_revive(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    data = callback.data.split("_")
    nickname = data[2]
    user_id = int(data[3])
    
    await bot.send_message(
        chat_id=user_id,
        text=f"❌ **Заявка на разбан отклонена.**\nПлатёж не найден."
    )
    await callback.message.edit_text(f"❌ Отклонено.")

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
    if await state.get_state() == "waiting_admin_reply":
        data = await state.get_data()
        user_id = data.get('reply_user_id')
        if user_id:
            await bot.send_message(user_id, f"📬 **Ответ админа:**\n\n{message.text}")
            await message.answer("✅ Ответ отправлен!")
            await state.clear()

# ========== ЗАПУСК ==========
async def main():
    print("╔══════════════════════════════════════════╗")
    print("║   🚀 AhilesVanilla Бот Запущен на Render ║")
    print("║   👑 Админ-панель: /admin               ║")
    print("║   🛡️ Блокировка игроков: есть           ║")
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
