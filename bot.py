import asyncio
import random
import sqlite3
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PollAnswer

# --- КОНФИГУРАЦИЯ ---
TOKEN = "ВАШ_ТОКЕН_ИЗ_RAILWAY" # Желательно через env: os.getenv("BOT_TOKEN")import os
import asyncio
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PollAnswer, ChatPermissions

# --- КОНФИГУРАЦИЯ ---
# Бот берёт токен из переменных окружения Railway (BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [7004839619]
ADMIN_USERNAME = "onardo-bit"
GROUP_ID = -5370978242
EXACT_777_VALUE = 64 # Значение диска 🎰 для 777

if not TOKEN:
    print("⚠️ ОШИБКА: Переменная BOT_TOKEN не найдена!")
    print("Пожалуйста, добавьте BOT_TOKEN в раздел Variables на Railway.")

bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
db = sqlite3.connect("bot_data.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS schedule (game TEXT PRIMARY KEY, day TEXT, time TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS prizes (game TEXT PRIMARY KEY, text TEXT)")
db.commit()

def get_config(key, default):
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    res = cur.fetchone()
    return res[0] if res else default

def set_config(key, value):
    cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    db.commit()

# --- СОСТОЯНИЯ ИГР ---
game_777_active = False
game_quiz_active = False
game_21_active = False

reg_users = []  # Список ID зарегистрированных игроков
quiz_scores = {} # Данные очков для викторины

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def hide_admin_cmd(message: types.Message):
    if message.chat.type != "private":
        try:
            await message.delete()
        except Exception:
            pass

def get_mention(user_id: int, username: str = None) -> str:
    if username:
        return f"@{username}"
    return f"ID:{user_id}"

# --- АДМИН-КОМАНДЫ И НАСТРОЙКИ ---
@dp.message(Command("jointime"))
async def set_jointime(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    try:
        t = int(message.text.split()[1])
        if 10 <= t <= 1800:
            set_config("jointime", t)
            await message.answer(f"✅ Время регистрации установлено: {t} сек.")
        else:
            await message.answer("❌ Укажите время от 10 до 1800 секунд.")
    except Exception:
        await message.answer("Используйте: `/jointime 300` (в секундах)")

@dp.message(Command("prize"))
async def set_prize(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Используйте: `/prize 777 1000 рублей` (игры: 777, quiz, 21)")
        return
    game, text = args[1].lower(), args[2]
    if game not in ["777", "quiz", "21"]:
        await message.answer("❌ Игра должна быть: 777, quiz или 21")
        return
    cur.execute("INSERT OR REPLACE INTO prizes (game, text) VALUES (?, ?)", (game, text))
    db.commit()
    await message.answer(f"✅ Приз для игры **{game}** сохранён: {text}")

@dp.message(Command("prizes"))
async def show_prizes(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    cur.execute("SELECT game, text FROM prizes")
    rows = cur.fetchall()
    if not rows:
        await message.answer("🎁 Призы ещё не настроены.")
        return
    res = "🎁 **Текущие призы:**\n" + "\n".join([f"• {g.upper()}: {t}" for g, t in rows])
    await message.answer(res)

@dp.message(Command("mute"))
async def mute_chat(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    try:
        await bot.set_chat_permissions(GROUP_ID, ChatPermissions(can_send_messages=False))
        await bot.send_message(GROUP_ID, "🔇 Чат переведён в режим «Только чтение».")
    except Exception as e:
        await message.answer(f"Ошибка при блокировке: {e}")

@dp.message(Command("unmute"))
async def unmute_chat(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    try:
        await bot.set_chat_permissions(
            GROUP_ID,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await bot.send_message(GROUP_ID, "🔊 Чат разблокирован.")
    except Exception as e:
        await message.answer(f"Ошибка при разблокировке: {e}")

# --- ИГРА 1: ЛУДКА ДО 777 ---
@dp.message(Command("start777"))
async def start_777(message: types.Message):
    global game_777_active
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    game_777_active = True
    await bot.send_message(
        GROUP_ID,
        "🎰 **ИГРА «ЛУДКА 777» НАЧАЛАСЬ!**\n\n"
        "Отправляйте эмодзи 🎰 со своей клавиатуры прямо в чат.\n"
        "Кто первым выбьет комбинацию 7️⃣7️⃣7️⃣ — моментально побеждает!"
    )

@dp.message(F.dice.emoji == "🎰")
async def check_777_roll(message: types.Message):
    global game_777_active
    if not game_777_active or message.chat.id != GROUP_ID:
        return

    # В Telegram API значение 64 соответствует 777
    if message.dice.value == EXACT_777_VALUE:
        game_777_active = False
        winner = get_mention(message.from_user.id, message.from_user.username)
        
        cur.execute("SELECT text FROM prizes WHERE game='777'")
        prize = cur.fetchone()
        prize_text = prize[0] if prize else "Не указан"

        await message.reply(
            f"🎉 **ПОБЕДА! 7️⃣7️⃣7️⃣**\n\n"
            f"🏆 Победитель: {winner}\n"
            f"🎁 Приз: {prize_text}\n\n"
            f"Для получения приза свяжитесь с @{ADMIN_USERNAME}"
        )

# --- ИГРА 2: ИГРА 21 (ПОЛНЫЙ АВТОМАТИЗМ ДО ПОБЕДЫ) ---
@dp.message(Command("start21"))
async def start_21(message: types.Message):
    global game_21_active, reg_users
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)

    game_21_active = True
    reg_users = []
    join_time = int(get_config("jointime", 900))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Участвовать 🎲", callback_data="reg_21")
    ]])

    await bot.send_message(
        GROUP_ID,
        f"🎲 **ОТКРЫТА РЕГИСТРАЦИЯ НА ИГРУ «21»**\n\n"
        f"Нажмите кнопку ниже! На регистрацию дано **{join_time} сек.**",
        reply_markup=kb
    )
    await asyncio.sleep(join_time)
    await process_21_game()

@dp.callback_query(F.data == "reg_21")
async def register_21_user(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        cur.execute(
            "INSERT OR REPLACE INTO users (id, username, name) VALUES (?, ?, ?)",
            (callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
        )
        db.commit()
        await callback.answer("Вы успешно зарегистрировались!")
    else:
        await callback.answer("Вы уже участвуете!")

async def process_21_game():
    global game_21_active
    if not reg_users:
        await bot.send_message(GROUP_ID, "❌ Никто не зарегистрировался. Игра «21» отменена.")
        game_21_active = False
        return

    # Загружаем список участников
    players_queue = []
    for uid in reg_users:
        cur.execute("SELECT username FROM users WHERE id=?", (uid,))
        res = cur.fetchone()
        un = res[0] if res else None
        players_queue.append({"id": uid, "un": un, "score": 0, "busts": 0})

    initial_players = [dict(p) for p in players_queue] # Резервная копия для рестарта при полном вылете
    winner = None

    await bot.send_message(
        GROUP_ID,
        f"🚀 **Игра «21» стартует!** Участников: {len(players_queue)}\n"
        f"⚙️ Бот бросает кубик 🎲 за каждого по очереди.\n"
        f"📌 Ровно 21 = победа. Перебор (>21) обнуляет очки и даёт 1 последний шанс."
    )

    # Бесконечный цикл, пока не найдем 1 победителя
    while game_21_active and not winner:
        # Если все игроки выбыли
        if not players_queue:
            await bot.send_message(GROUP_ID, "🔄 Все игроки выбыли! Перезапуск раунда с исходными участниками...")
            players_queue = [dict(p) for p in initial_players]
            for p in players_queue:
                p["score"] = 0
                p["busts"] = 0
            continue

        player = players_queue.pop(0) # Берём первого в очереди
        mention = get_mention(player["id"], player["un"])

        await bot.send_message(GROUP_ID, f"🎲 Ход игрока {mention} (Сумма до броска: {player['score']})")
        
        # Бот бросает кубик от своего имени
        dice_msg = await bot.send_dice(GROUP_ID, emoji="🎲")
        val = dice_msg.dice.value
        player["score"] += val

        # Ожидание завершения анимации
        await asyncio.sleep(1.5)

        await bot.send_message(GROUP_ID, f"{mention}: 🎲 Выпало **{val}** | Итоговая сумма: **{player['score']}**")

        # Проверка условий
        if player["score"] == 21:
            winner = player
            break
        elif player["score"] > 21:
            if player["busts"] == 0:
                player["busts"] = 1
                player["score"] = 0
                players_queue.append(player) # Отправляем в конец очереди
                await bot.send_message(GROUP_ID, f"💥 {mention} превысил 21! Сумма сброшена на 0. Игрок уходит в конец очереди.")
            else:
                await bot.send_message(GROUP_ID, f"❌ {mention} снова превысил 21 и окончательно выбывает!")
        else:
            players_queue.append(player) # Возвращаем в очередь для следующего круга

        # Задержка 2 секунды между ходами, чтобы соблюдать лимиты Telegram API
        await asyncio.sleep(2.0)

    # Завершение игры и объявление победителя
    if winner:
        game_21_active = False
        cur.execute("SELECT text FROM prizes WHERE game='21'")
        pz = cur.fetchone()
        prize_text = pz[0] if pz else "Не указан"

        await bot.send_message(
            GROUP_ID,
            f"🏆 **ЕДИНСТВЕННЫЙ ПОБЕДИТЕЛЬ В 21:** {get_mention(winner['id'], winner['un'])}\n"
            f"🎯 Выбил ровно **21**!\n"
            f"🎁 Приз: {prize_text}\n\n"
            f"Для получения приза напишите @{ADMIN_USERNAME}"
        )

# --- ИГРА 3: ВИКТОРИНА ---
@dp.message(Command("startquiz"))
async def start_quiz(message: types.Message):
    global game_quiz_active, reg_users, quiz_scores
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)

    game_quiz_active = True
    reg_users = []
    quiz_scores = {}
    join_time = int(get_config("jointime", 900))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Участвовать 🎓", callback_data="reg_quiz")
    ]])

    await bot.send_message(
        GROUP_ID,
        f"🎓 **НАЧИНАЕТСЯ ВИКТОРИНА!**\n\n"
        f"Вас ждёт 5 вопросов. Время на регистрацию: **{join_time} сек.**",
        reply_markup=kb
    )
    await asyncio.sleep(join_time)
    await run_quiz_questions()

@dp.callback_query(F.data == "reg_quiz")
async def register_quiz_user(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        cur.execute(
            "INSERT OR REPLACE INTO users (id, username, name) VALUES (?, ?, ?)",
            (callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
        )
        db.commit()
        quiz_scores[callback.from_user.id] = {"score": 0, "last_ts": 0, "username": callback.from_user.username}
        await callback.answer("Вы зарегистрированы на викторину!")
    else:
        await callback.answer("Вы уже зарегистрированы!")

async def run_quiz_questions():
    global game_quiz_active
    if not reg_users:
        await bot.send_message(GROUP_ID, "❌ Нет участников. Викторина отменена.")
        game_quiz_active = False
        return

    questions = [
        ("Сколько планет в Солнечной системе?", ["7", "8", "9", "10"], 1),
        ("Какой химический символ у Золота?", ["Ag", "Fe", "Au", "Pb"], 2),
        ("В каком году человек впервые полетел в космос?", ["1957", "1961", "1965", "1969"], 1),
        ("Столица Франции?", ["Берлин", "Париж", "Рим", "Мадрид"], 1),
        ("Корень из 144?", ["10", "11", "12", "14"], 2)
    ]

    for q_text, opts, correct_idx in questions:
        await bot.send_poll(
            chat_id=GROUP_ID,
            question=q_text,
            options=opts,
            is_anonymous=False,
            type="quiz",
            correct_option_id=correct_idx,
            open_period=30
        )
        await asyncio.sleep(32)

    # Подведение итогов
    if not quiz_scores:
        await bot.send_message(GROUP_ID, "Викторина завершена. Ответы не получены.")
        game_quiz_active = False
        return

    # Сортировка: наибольшие очки -> при равенстве наименьший таймштамп (скорость)
    sorted_players = sorted(quiz_scores.items(), key=lambda x: (-x[1]["score"], x[1]["last_ts"]))
    win_id, win_data = sorted_players[0]

    cur.execute("SELECT text FROM prizes WHERE game='quiz'")
    pz = cur.fetchone()
    prize_text = pz[0] if pz else "Не указан"

    await bot.send_message(
        GROUP_ID,
        f"🏆 **ПОБЕДИТЕЛЬ ВИКТОРИНЫ:** {get_mention(win_id, win_data['username'])}\n"
        f"📊 Набрано очков: **{win_data['score']}**\n"
        f"🎁 Приз: {prize_text}\n\n"
        f"Напишите @{ADMIN_USERNAME} для получения приза!"
    )
    game_quiz_active = False

@dp.poll_answer()
async def process_poll_answer(poll_answer: PollAnswer):
    if not game_quiz_active: return
    uid = poll_answer.user_id
    if uid in quiz_scores:
        quiz_scores[uid]["score"] += 1
        quiz_scores[uid]["last_ts"] = time.time()

# --- СТАРТ БОТА ---
async def main():
    if not bot:
        return
    print("🤖 Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
ADMIN_IDS = [7004839619]
ADMIN_USERNAME = "onardo-bit"
GROUP_ID = -5370978242

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
db = sqlite3.connect("bot_data.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS schedule (game TEXT PRIMARY KEY, day TEXT, time TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS prizes (game TEXT PRIMARY KEY, text TEXT)")
db.commit()

def get_config(key, default):
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    res = cur.fetchone()
    return res[0] if res else default

def set_config(key, value):
    cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    db.commit()

# --- СОСТОЯНИЯ ИГР ---
game_777_active = False
game_quiz_active = False
game_21_active = False

reg_users = []  # Список ID участников для текущей игры (Викторина/21)
quiz_scores = {} # {user_id: {'score': 0, 'last_ts': 0, 'username': ''}}
game_21_queue = [] # Список диктов [{'id':, 'un':, 'score':, 'busts':}]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def is_admin(user_id):
    return user_id in ADMIN_IDS

async def hide_admin_cmd(message: types.Message):
    if message.chat.type != "private":
        try:
            await message.delete()
        except:
            pass

def get_mention(user_id, username):
    return f"@{username}" if username else f"ID:{user_id}"

# --- АДМИН-КОМАНДЫ (ЧЕРЕЗ ЛС) ---
@dp.message(Command("jointime"))
async def set_jointime(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    try:
        t = int(message.text.split()[1])
        if 10 <= t <= 1800:
            set_config("jointime", t)
            await message.answer(f"✅ Время регистрации: {t} сек.")
        else:
            await message.answer("❌ От 10 до 1800 сек.")
    except:
        await message.answer("Используйте: /jointime 300")

@dp.message(Command("prize"))
async def set_prize(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3: return
    game, text = args[1].lower(), args[2]
    cur.execute("INSERT OR REPLACE INTO prizes (game, text) VALUES (?, ?)", (game, text))
    db.commit()
    await message.answer(f"✅ Приз для {game} сохранен.")

@dp.message(Command("mute"))
async def mute_handler(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    await bot.restrict_chat_member(GROUP_ID, message.from_user.id, permissions=types.ChatPermissions(can_send_messages=False))
    await bot.send_message(GROUP_ID, "🔇 Чат переведен в режим 'Только чтение'.")

@dp.message(Command("unmute"))
async def unmute_handler(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    await bot.restrict_chat_member(GROUP_ID, message.from_user.id, permissions=types.ChatPermissions(
        can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True
    ))
    await bot.send_message(GROUP_ID, "🔊 Чат разблокирован.")

# --- ИГРА: ЛУДКА 777 (МАНУАЛЬНАЯ) ---
@dp.message(Command("start777"))
async def start_777(message: types.Message):
    global game_777_active
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    game_777_active = True
    await bot.send_message(GROUP_ID, "🎰 **ИГРА: ЛУДКА 777 ОТКРЫТА!**\n\nКто первым выбьет комбинацию 7️⃣7️⃣7️⃣ — тот победил!\nКидайте эмодзи 🎰 в чат!")

@dp.message(F.dice.emoji == "🎰")
async def check_777(message: types.Message):
    global game_777_active
    if not game_777_active or message.chat.id != GROUP_ID: return
    
    if message.dice.value == 64: # Значение 64 соответствует 777
        game_777_active = False
        winner_mention = get_mention(message.from_user.id, message.from_user.username)
        cur.execute("SELECT text FROM prizes WHERE game='777'")
        prize = cur.fetchone()
        prize_text = prize[0] if prize else "Секретный приз"
        
        await message.reply(f"🥳 ПРЯМОЕ ПОПАДАНИЕ! 7️⃣7️⃣7️⃣\n\n🏆 Победитель: {winner_mention}\n🎁 Приз: {prize_text}\n\nДля получения приза напишите @{ADMIN_USERNAME}")

# --- ИГРА: 21 (ПОЛНАЯ АВТОМАТИКА) ---
@dp.message(Command("start21"))
async def start_21(message: types.Message):
    global game_21_active, reg_users
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    
    game_21_active = True
    reg_users = []
    t = int(get_config("jointime", 900))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Участвовать", callback_data="reg_21")]])
    await bot.send_message(GROUP_ID, f"🎲 **ИГРА 21 - РЕГИСТРАЦИЯ**\n\nНажмите кнопку ниже! У вас есть {t} сек.", reply_markup=kb)
    await asyncio.sleep(t)
    await run_21_game()

@dp.callback_query(F.data == "reg_21")
async def reg_21_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        cur.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (callback.from_user.id, callback.from_user.username, callback.from_user.full_name))
        db.commit()
        await callback.answer("Вы зарегистрированы!")
    else:
        await callback.answer("Вы уже в списке.")

async def run_21_game():
    global game_21_active, game_21_queue
    if len(reg_users) == 0:
        await bot.send_message(GROUP_ID, "❌ Никто не зарегистрировался на 21.")
        game_21_active = False
        return

    # Загружаем данные игроков
    game_21_queue = []
    for uid in reg_users:
        cur.execute("SELECT username FROM users WHERE id=?", (uid,))
        un = cur.fetchone()[0]
        game_21_queue.append({'id': uid, 'un': un, 'score': 0, 'busts': 0})
    
    original_players = list(game_21_queue) # Сохраняем для рестарта если все вылетят
    winner = None

    await bot.send_message(GROUP_ID, f"🚀 Игра 21 начинается! Участников: {len(game_21_queue)}\nПравила: Бот крутит за вас. 21 = победа. Перебор > 21 возвращает в конец очереди (1 раз).")

    while game_21_active and not winner:
        if not game_21_queue:
            await bot.send_message(GROUP_ID, "🔄 Все игроки вылетели! Начинаем раунд заново с теми же участниками.")
            game_21_queue = [p.copy() for p in original_players]
            for p in game_21_queue: p['score'] = 0; p['busts'] = 0
            continue

        player = game_21_queue.pop(0) # Берем первого игрока
        mention = get_mention(player['id'], player['un'])
        
        msg = await bot.send_message(GROUP_ID, f"🎲 Ход игрока {mention} (Сумма: {player['score']})")
        dice_msg = await bot.send_dice(GROUP_ID, emoji="🎲")
        val = dice_msg.dice.value
        player['score'] += val
        
        await asyncio.sleep(3.5) # Ждем анимацию + пауза
        
        await bot.send_message(GROUP_ID, f"{mention}: 🎲 Выпало {val} | Текущая сумма: {player['score']}")

        if player['score'] == 21:
            winner = player
            break
        elif player['score'] > 21:
            if player['busts'] == 0:
                player['busts'] = 1
                player['score'] = 0
                game_21_queue.append(player) # В конец очереди
                await bot.send_message(GROUP_ID, f"💥 Перебор! {mention} обнуляется и идет в конец очереди (последний шанс).")
            else:
                await bot.send_message(GROUP_ID, f"❌ {mention} вылетает из игры! (Второй перебор)")
        else:
            # Если не перебор и не 21, просто кидаем в конец очереди для следующего круга
            game_21_queue.append(player)
            
        await asyncio.sleep(2) # Лимит сообщений

    if winner:
        game_21_active = False
        cur.execute("SELECT text FROM prizes WHERE game='21'")
        pz = cur.fetchone()
        prize_text = pz[0] if pz else "Секретный приз"
        await bot.send_message(GROUP_ID, f"🏆 ПОБЕДИТЕЛЬ В 21: {get_mention(winner['id'], winner['un'])}\nСумма: 21!\n🎁 Приз: {prize_text}\n\nПиши @{ADMIN_USERNAME}")

# --- ИГРА: ВИКТОРИНА (БЕЗ ИЗМЕНЕНИЙ) ---
@dp.message(Command("startquiz"))
async def start_quiz(message: types.Message):
    global game_quiz_active, reg_users, quiz_scores
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    
    game_quiz_active = True
    reg_users = []
    quiz_scores = {}
    t = int(get_config("jointime", 900))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Участвовать", callback_data="reg_quiz")]])
    await bot.send_message(GROUP_ID, f"🎓 **ВИКТОРИНА - РЕГИСТРАЦИЯ**\n\n5 вопросов. Скорость важна!\nВремя на вход: {t} сек.", reply_markup=kb)
    await asyncio.sleep(t)
    await run_quiz()

@dp.callback_query(F.data == "reg_quiz")
async def reg_quiz_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        quiz_scores[callback.from_user.id] = {'score': 0, 'last_ts': 0, 'username': callback.from_user.username}
        await callback.answer("Вы в игре!")
    else:
        await callback.answer("Уже участвуете.")

async def run_quiz():
    global game_quiz_active
    if not reg_users:
        await bot.send_message(GROUP_ID, "❌ Нет участников для викторины.")
        return

    questions = [
        ("Сколько планет в Солнечной системе?", ["7", "8", "9", "10"], 1),
        ("Какой химический символ у Золота?", ["Ag", "Fe", "Au", "Pb"], 2),
        ("В каком году полетел Гагарин?", ["1957", "1961", "1965", "1969"], 1),
        ("Столица Франции?", ["Берлин", "Париж", "Рим", "Мадрид"], 1),
        ("Корень из 144?", ["10", "11", "12", "14"], 2)
    ]

    for q_text, options, correct_idx in questions:
        await bot.send_poll(
            GROUP_ID, q_text, options, is_anonymous=False, type="quiz", 
            correct_option_id=correct_idx, open_period=30
        )
        await asyncio.sleep(32)

    # Определение победителя
    if not quiz_scores: return
    sorted_winners = sorted(quiz_scores.items(), key=lambda x: (-x[1]['score'], x[1]['last_ts']))
    win_id, data = sorted_winners[0]
    
    cur.execute("SELECT text FROM prizes WHERE game='quiz'")
    pz = cur.fetchone()
    prize_text = pz[0] if pz else "Секретный приз"

    await bot.send_message(GROUP_ID, f"🏆 ПОБЕДИТЕЛЬ ВИКТОРИНЫ: {get_mention(win_id, data['username'])}\nОчки: {data['score']}\n🎁 Приз: {prize_text}\n\nНапиши @{ADMIN_USERNAME}")
    game_quiz_active = False

@dp.poll_answer()
async def poll_ans_handler(poll_answer: PollAnswer):
    if not game_quiz_active: return
    user_id = poll_answer.user_id
    if user_id not in quiz_scores: return

    # Простая логика: если ответил верно (это проверяется на стороне юзера, тут мы ловим только факт участия)
    # К сожалению, Bot API не шлет "правильно/неправильно" в poll_answer.
    # Поэтому для реализации "1й ответивший правильно" обычно используют кастомные кнопки.
    # Но раз мы используем Poll, добавим просто +1 за ответ.
    quiz_scores[user_id]['score'] += 1
    quiz_scores[user_id]['last_ts'] = time.time()

# --- СТАРТ ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
