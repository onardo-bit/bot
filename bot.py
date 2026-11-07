# ============================================
# ИГРОВОЙ БОТ ДЛЯ TELEGRAM
# Зависимость: pip install aiogram
# Запуск: python bot.py
# ============================================

import asyncio
import sqlite3
import random
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, PollAnswer,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.enums import ParseMode, PollType

# ============================================
# НАСТРОЙКИ — ЗАПОЛНИ СВОИ ДАННЫЕ
# ============================================
TOKEN = "9098594468:AAHYZT21NS_IYsc3BlN6w8bmP8y0F4ZvWeo"
ADMIN_IDS = [7004839619]  # Твой ID через @userinfobot
GROUP_ID = -5370978242  # ID группы (бот покажет сам при /start)

# ============================================
# БАЗА ДАННЫХ (SQLite, встроен в Python)
# ============================================
DB_NAME = "game_bot.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        wins INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT,
        day TEXT,
        time TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS prizes (
        game TEXT PRIMARY KEY,
        prize TEXT
    )""")
    conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
              (user_id, username))
    c.execute("UPDATE users SET username = ? WHERE user_id = ?",
              (username, user_id))
    conn.commit()
    conn.close()

def is_registered(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_win(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_prize(game):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT prize FROM prizes WHERE game = ?", (game,))
    row = c.fetchone()
    conn.close()
    return row["prize"] if row else "Не назначен"

def set_prize(game, prize):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO prizes (game, prize) VALUES (?, ?)",
              (game, prize))
    conn.commit()
    conn.close()

def get_schedule():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM schedule")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_schedule(game, day, time):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO schedule (game, day, time) VALUES (?, ?, ?)",
              (game, day, time))
    conn.commit()
    conn.close()

def remove_schedule(game):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM schedule WHERE game = ?", (game,))
    conn.commit()
    conn.close()

def clear_schedule():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM schedule")
    conn.commit()
    conn.close()

# ============================================
# ВОПРОСЫ ВИКТОРИНЫ (школьные)
# ============================================
QUESTIONS = [
    {"q": "Сколько будет 7 × 8?", "o": ["54", "56", "58", "64"], "c": 1},
    {"q": "Столица Франции?", "o": ["Лондон", "Берлин", "Париж", "Мадрид"], "c": 2},
    {"q": "Сколько континентов на Земле?", "o": ["5", "6", "7", "8"], "c": 2},
    {"q": "Кто написал «Войну и мир»?", "o": ["Достоевский", "Толстой", "Чехов", "Пушкин"], "c": 1},
    {"q": "Формула воды?", "o": ["CO2", "H2O", "NaCl", "O2"], "c": 1},
    {"q": "Сколько дней в високосном году?", "o": ["364", "365", "366", "367"], "c": 2},
    {"q": "Самая длинная река в мире?", "o": ["Амазонка", "Нил", "Миссисипи", "Янцзы"], "c": 1},
    {"q": "Какой газ мы вдыхаем?", "o": ["CO2", "N2", "O2", "H2"], "c": 2},
    {"q": "Сколько планет в Солнечной системе?", "o": ["7", "8", "9", "10"], "c": 1},
    {"q": "В каком году человек впервые полетел в космос?", "o": ["1957", "1961", "1965", "1969"], "c": 1},
    {"q": "Столица Японии?", "o": ["Пекин", "Сеул", "Токио", "Бангкок"], "c": 2},
    {"q": "Сколько будет 144 ÷ 12?", "o": ["10", "11", "12", "14"], "c": 2},
    {"q": "Какой океан самый большой?", "o": ["Атлантический", "Индийский", "Тихий", "Северный Ледовитый"], "c": 2},
    {"q": "Кто изобрёл лампочку?", "o": ["Тесла", "Эдисон", "Белл", "Ньютон"], "c": 1},
    {"q": "Сколько букв в русском алфавите?", "o": ["30", "32", "33", "34"], "c": 2},
    {"q": "Какая планета ближе всего к Солнцу?", "o": ["Венера", "Марс", "Меркурий", "Земля"], "c": 2},
    {"q": "Сколько будет 15² ?", "o": ["200", "215", "225", "250"], "c": 2},
    {"q": "Какой материк самый холодный?", "o": ["Гренландия", "Антарктида", "Арктика", "Сибирь"], "c": 1},
    {"q": "Сколько цветов в радуге?", "o": ["5", "6", "7", "8"], "c": 2},
    {"q": "Кто написал «Евгения Онегина»?", "o": ["Лермонтов", "Гоголь", "Пушкин", "Тургенев"], "c": 2},
]

# ============================================
# СОСТОЯНИЕ ИГР
# ============================================
active_games = {}  # {"777": {...}, "quiz": {...}, "21": {...}}
TIMEZONE_OFFSET = 3  # Москва по умолчанию

# ============================================
# БОТ И ДИСПЕТЧЕР
# ============================================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ============================================
# КОМАНДЫ
# ============================================

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    global GROUP_ID
    if msg.chat.type in ("group", "supergroup"):
        GROUP_ID = msg.chat.id
        await msg.answer(
            f"👋 Привет! Я игровой бот.\n"
            f"ID этой группы: {msg.chat.id}\n"
            f"Вставь его в код в переменную GROUP_ID.\n\n"
            f"Игры:\n"
            f"🎰 Лудка до 777\n"
            f"📚 Викторина\n"
            f"🎲 21\n\n"
            f"Админ запускает: /start777 /startquiz /start21"
        )
    else:
        await msg.answer(
            "👋 Привет! Добавь меня в группу и напиши /start там.\n"
            "Команды: /help"
        )

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "🎮 ИГРЫ:\n"
        "🎰 /start777 — Лудка до 777\n"
        "📚 /startquiz — Викторина\n"
        "🎲 /start21 — Игра 21\n\n"
        "📋 /schedule — Расписание\n"
        "🎁 /prizes — Призы\n"
        "👤 /myprofile — Мой профиль"
    )

@dp.message(Command("myprofile"))
async def cmd_profile(msg: Message):
    stats = get_user_stats(msg.from_user.id)
    if not stats:
        await msg.answer("❌ Ты ещё не зарегистрирован. Нажми «Участвовать» в любой игре (викторина или 21).")
        return
    reg = "✅" if stats else "❌"
    await msg.answer(
        f"👤 Профиль @{stats['username']}\n"
        f"📝 Регистрация: {reg}\n"
        f"🏆 Побед: {stats['wins']}"
    )

# ============================================
# ЗАПУСК ИГР (АДМИН)
# ============================================

@dp.message(Command("start777"))
async def cmd_start777(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    prize = get_prize("777")
    active_games["777"] = {"players": [], "phase": "join"}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Участвовать", callback_data="join_777")]
    ])
    await msg.answer(
        f"🎰 ЛУДКА ДО 777!\n"
        f"🎁 Приз: {prize}\n"
        f"Регистрация не нужна!\n"
        f"Нажми кнопку. Набор: 2 минуты.",
        reply_markup=kb
    )
    await asyncio.sleep(120)
    await run_777(msg.chat.id)

@dp.message(Command("startquiz"))
async def cmd_startquiz(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    prize = get_prize("quiz")
    active_games["quiz"] = {"players": [], "phase": "join", "scores": {}}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Участвовать", callback_data="join_quiz")]
    ])
    await msg.answer(
        f"📚 ВИКТОРИНА!\n"
        f"🎁 Приз: {prize}\n"
        f"5 вопросов, 30 сек на каждый.\n"
        f"Нужна регистрация (кнопка).\n"
        f"Набор: 2 минуты.",
        reply_markup=kb
    )
    await asyncio.sleep(120)
    await run_quiz(msg.chat.id)

@dp.message(Command("start21"))
async def cmd_start21(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    prize = get_prize("21")
    active_games["21"] = {"players": [], "phase": "join"}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Участвовать", callback_data="join_21")]
    ])
    await msg.answer(
        f"🎲 ИГРА 21!\n"
        f"🎁 Приз: {prize}\n"
        f"Кидаешь по кругу, один бросок за ход.\n"
        f"Набрал 21 — победил.\n"
        f"Перебрал — вторая попытка.\n"
        f"Нужна регистрация (кнопка).\n"
        f"Набор: 2 минуты.",
        reply_markup=kb
    )
    await asyncio.sleep(120)
    await run_21(msg.chat.id)

# ============================================
# КНОПКА «УЧАСТВОВАТЬ»
# ============================================

@dp.callback_query(F.data.startswith("join_"))
async def cb_join(call: CallbackQuery):
    game = call.data.split("_")[1]
    uid = call.from_user.id
    uname = call.from_user.username or call.from_user.first_name

    if game not in active_games or active_games[game]["phase"] != "join":
        await call.answer("⏳ Набор закрыт!", show_alert=True)
        return

    if uid in [p["id"] for p in active_games[game]["players"]]:
        await call.answer("✅ Ты уже в игре!", show_alert=True)
        return

    if game in ("quiz", "21"):
        if not is_registered(uid):
            register_user(uid, uname)
            await call.answer(f"✅ Зарегистрирован и в игре!", show_alert=True)
            await bot.send_message(
                GROUP_ID, f"🆕 @{uname} зарегистрирован и в игре!"
            )
        else:
            await call.answer("✅ Ты в игре!", show_alert=True)
            await bot.send_message(
                GROUP_ID, f"✅ @{uname} в игре!"
            )
    else:
        await call.answer("✅ Ты в игре!", show_alert=True)
        await bot.send_message(
            GROUP_ID, f"✅ @{uname} в игре!"
        )

    active_games[game]["players"].append({"id": uid, "name": uname})

# ============================================
# ИГРА 1: ЛУДКА ДО 777
# ============================================

async def run_777(chat_id):
    game = active_games.get("777")
    if not game or not game["players"]:
        await bot.send_message(chat_id, "😔 Никто не участвует. Игра отменена.")
        return

    game["phase"] = "playing"
    await bot.send_message(chat_id, "🎰 Набор закрыт! Крутим слоты...")
    await asyncio.sleep(2)

    jackpot_values = {1, 22, 43, 64}
    winners = []

    for p in game["players"]:
        msg = await bot.send_dice(chat_id, emoji="🎰")
        val = msg.dice.value
        is_jackpot = val in jackpot_values
        result = "🎉 ДЖЕКПОТ!" if is_jackpot else "Не повезло"
        await bot.send_message(
            chat_id, f"🎰 @{p['name']}: {result}"
        )
        if is_jackpot:
            winners.append(p)
        await asyncio.sleep(2)

    if len(winners) == 1:
        await announce_winner(chat_id, winners[0], "777")
    elif len(winners) > 1:
        await bot.send_message(chat_id, "🔥 Несколько джекпотов! Перекрут...")
        await asyncio.sleep(2)
        final_winner = await tiebreak_slots(chat_id, winners)
        await announce_winner(chat_id, final_winner, "777")
    else:
        await bot.send_message(chat_id, "😔 Джекпот не выпал! Попробуйте в следующий раз.")

    active_games.pop("777", None)

async def tiebreak_slots(chat_id, players):
    jackpot_values = {1, 22, 43, 64}
    while len(players) > 1:
        new_winners = []
        for p in players:
            msg = await bot.send_dice(chat_id, emoji="🎰")
            val = msg.dice.value
            if val in jackpot_values:
                new_winners.append(p)
            await asyncio.sleep(2)
        if len(new_winners) == 1:
            return new_winners[0]
        elif len(new_winners) == 0:
            players = players  # все крутят ещё раз
        else:
            players = new_winners
    return players[0]

# ============================================
# ИГРА 2: ВИКТОРИНА
# ============================================

async def run_quiz(chat_id):
    game = active_games.get("quiz")
    if not game or not game["players"]:
        await bot.send_message(chat_id, "😔 Никто не участвует. Игра отменена.")
        return

    game["phase"] = "playing"
    scores = {p["id"]: 0 for p in game["players"]}
    first_correct = {}

    await bot.send_message(chat_id, "📚 Набор закрыт! Начинаем викторину...")
    await asyncio.sleep(2)

    selected = random.sample(QUESTIONS, min(5, len(QUESTIONS)))

    for i, q in enumerate(selected):
        await bot.send_message(chat_id, f"❓ Вопрос {i+1}/5")
        await asyncio.sleep(1)

        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=q["q"],
            options=q["o"],
            type=PollType.QUIZ,
            correct_option_id=q["c"],
            is_anonymous=False,
            open_period=30
        )

        game["current_poll"] = poll_msg.poll.id
        game["correct"] = q["c"]
        game["answered"] = {}
        await asyncio.sleep(31)

        for uid, data in game["answered"].items():
            if data["correct"]:
                scores[uid] += 1
                if data["first"]:
                    scores[uid] += 1

        leaderboard = sorted(
            [(uid, sc) for uid, sc in scores.items()],
            key=lambda x: -x[1]
        )
        top = leaderboard[:3]
        lb_text = "\n".join(
            [f"  {j+1}. @{get_name(game, uid)} — {sc} баллов"
             for j, (uid, sc) in enumerate(top)]
        )
        await bot.send_message(chat_id, f"📊 После вопроса {i+1}:\n{lb_text}")
        await asyncio.sleep(2)

    best_score = max(scores.values()) if scores else 0
    winners = [uid for uid, sc in scores.items() if sc == best_score]

    if len(winners) == 1:
        winner = get_player(game, winners[0])
        await announce_winner(chat_id, winner, "quiz")
    else:
        await bot.send_message(chat_id, "⚡ Ничья! Внезапная смерть — один вопрос!")
        await asyncio.sleep(2)
        tie_q = random.choice(QUESTIONS)
        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=tie_q["q"],
            options=tie_q["o"],
            type=PollType.QUIZ,
            correct_option_id=tie_q["c"],
            is_anonymous=False,
            open_period=30
        )
        game["current_poll"] = poll_msg.poll.id
        game["correct"] = tie_q["c"]
        game["answered"] = {}
        game["tie_players"] = winners
        await asyncio.sleep(31)

        tie_winners = [uid for uid, d in game["answered"].items()
                       if d["correct"] and uid in winners]
        if tie_winners:
            winner = get_player(game, tie_winners[0])
            await announce_winner(chat_id, winner, "quiz")
        else:
            await bot.send_message(chat_id, "😔 Никто не ответил правильно. Игра окончена.")

    active_games.pop("quiz", None)

def get_name(game, uid):
    for p in game["players"]:
        if p["id"] == uid:
            return p["name"]
    return str(uid)

def get_player(game, uid):
    for p in game["players"]:
        if p["id"] == uid:
            return p
    return {"id": uid, "name": str(uid)}

@dp.poll_answer()
async def handle_poll(poll_answer: PollAnswer):
    game = active_games.get("quiz")
    if not game or game["phase"] != "playing":
        return
    if not hasattr(game, "current_poll") and "current_poll" not in game:
        return
    if poll_answer.poll_id != game.get("current_poll"):
        return

    uid = poll_answer.user.id
    if uid not in [p["id"] for p in game["players"]]:
        return

    chosen = poll_answer.option_ids[0] if poll_answer.option_ids else -1
    is_correct = chosen == game["correct"]
    is_first = is_correct and not any(
        d["correct"] for d in game["answered"].values()
    )

    game["answered"][uid] = {"correct": is_correct, "first": is_first}

# ============================================
# ИГРА 3: 21
# ============================================

async def run_21(chat_id):
    game = active_games.get("21")
    if not game or not game["players"]:
        await bot.send_message(chat_id, "😔 Никто не участвует. Игра отменена.")
        return

    game["phase"] = "playing"
    random.shuffle(game["players"])
    queue = list(game["players"])
    sums = {p["id"]: 0 for p in queue}
    attempts = {p["id"]: 0 for p in queue}

    queue_text = "\n".join(
        [f"  {i+1}. @{p['name']}" for i, p in enumerate(queue)]
    )
    await bot.send_message(chat_id, f"📋 Очередь:\n{queue_text}\n🎲 Начинаем!")
    await asyncio.sleep(2)

    round_num = 1
    winner = None

    while queue and not winner:
        await bot.send_message(chat_id, f"--- Круг {round_num} ---")
        await asyncio.sleep(1)

        next_queue = []
        for p in queue:
            if p["id"] not in sums:
                continue

            dice_msg = await bot.send_dice(chat_id, emoji="🎲")
            val = dice_msg.dice.value
            sums[p["id"]] += val
            current_sum = sums[p["id"]]

            if current_sum == 21:
                await bot.send_message(
                    chat_id,
                    f"@{p['name']}: 🎲 {val} | Сумма: {current_sum} — 🏆 ПОБЕДА!"
                )
                winner = p
                break
            elif current_sum > 21:
                if attempts[p["id"]] >= 1:
                    await bot.send_message(
                        chat_id,
                        f"@{p['name']}: 🎲 {val} | Сумма: {current_sum} — 💀 Выбыл!"
                    )
                    del sums[p["id"]]
                else:
                    attempts[p["id"]] += 1
                    sums[p["id"]] = 0
                    await bot.send_message(
                        chat_id,
                        f"@{p['name']}: 🎲 {val} | Сумма: {current_sum} — 💀 Перебор! Вторая попытка в конце."
                    )
                    next_queue.append(p)
            else:
                await bot.send_message(
                    chat_id,
                    f"@{p['name']}: 🎲 {val} | Сумма: {current_sum}"
                )
                next_queue.append(p)

            await asyncio.sleep(2)

        if not winner:
            queue = next_queue
            round_num += 1

    if winner:
        await announce_winner(chat_id, winner, "21")
    else:
        await bot.send_message(chat_id, "😔 Все выбыли! Раунд заново.")
        active_games["21"] = {"players": game["players"], "phase": "join"}
        await run_21(chat_id)
        return

    active_games.pop("21", None)

# ============================================
# ОБЪЯВЛЕНИЕ ПОБЕДИТЕЛЯ
# ============================================

async def announce_winner(chat_id, player, game_name):
    prize = get_prize(game_name)
    add_win(player["id"])
    admin_mention = ", ".join([f"@{a}" for a in ADMIN_IDS]) if ADMIN_IDS else "@admin"
    await bot.send_message(
        chat_id,
        f"🏆 ПОБЕДИТЕЛЬ: @{player['name']}!\n"
        f"🎮 Игра: {game_name}\n"
        f"🎁 Приз: {prize}\n\n"
        f"{admin_mention}, вручите приз победителю!"
    )

# ============================================
# РАСПИСАНИЕ
# ============================================

@dp.message(Command("schedule"))
async def cmd_schedule(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    rows = get_schedule()
    if not rows:
        await msg.answer("📋 Расписание пусто.")
        return
    text = "📋 Расписание:\n"
    for r in rows:
        text += f"  {r['game']} — {r['day']} {r['time']}\n"
    await msg.answer(text)

@dp.message(Command("set"))
async def cmd_set(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    args = msg.text.split()
    if len(args) < 4:
        await msg.answer("Формат: /set 777 ПН 18:00")
        return
    game, day, time = args[1], args[2].upper(), args[3]
    if game not in ("777", "quiz", "21"):
        await msg.answer("Игра: 777, quiz или 21")
        return
    add_schedule(game, day, time)
    await msg.answer(f"✅ {game} добавлена: {day} {time}")

@dp.message(Command("remove"))
async def cmd_remove(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("Формат: /remove 777")
        return
    remove_schedule(args[1])
    await msg.answer(f"✅ {args[1]} убрана из расписания")

@dp.message(Command("clear_schedule"))
async def cmd_clear(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    clear_schedule()
    await msg.answer("✅ Расписание очищено")

@dp.message(Command("timezone"))
async def cmd_timezone(msg: Message):
    global TIMEZONE_OFFSET
    if not is_admin(msg.from_user.id):
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer(f"Текущий часовой пояс: UTC+{TIMEZONE_OFFSET}\nФормат: /timezone 3")
        return
    TIMEZONE_OFFSET = int(args[1])
    await msg.answer(f"✅ Часовой пояс: UTC+{TIMEZONE_OFFSET}")

# ============================================
# ПРИЗЫ
# ============================================

@dp.message(Command("prize"))
async def cmd_prize(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    args = msg.text.split(maxsplit=2)
    if len(args) < 3:
        await msg.answer("Формат: /prize 777 Звёздный подарок")
        return
    game, prize = args[1], args[2]
    if game not in ("777", "quiz", "21"):
        await msg.answer("Игра: 777, quiz или 21")
        return
    set_prize(game, prize)
    await msg.answer(f"✅ Приз для {game}: {prize}")

@dp.message(Command("prizes"))
async def cmd_prizes(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    text = "🎁 Призы:\n"
    for g in ("777", "quiz", "21"):
        text += f"  {g}: {get_prize(g)}\n"
    await msg.answer(text)

@dp.message(Command("delivered"))
async def cmd_delivered(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("Формат: /delivered @username")
        return
    await msg.answer(f"✅ Вручение {args[1]} отмечено!")

# ============================================
# ФОНОВОЕ РАСПИСАНИЕ
# ============================================

DAYS = {"ПН": 0, "ВТ": 1, "СР": 2, "ЧТ": 3, "ПТ": 4, "СБ": 5, "ВС": 6}

async def scheduler():
    from datetime import timezone, timedelta
    while True:
        tz = timezone(timedelta(hours=TIMEZONE_OFFSET))
        now = datetime.now(tz)
        current_day = now.strftime("%A")
        day_map = {
            "Monday": "ПН", "Tuesday": "ВТ", "Wednesday": "СР",
            "Thursday": "ЧТ", "Friday": "ПТ", "Saturday": "СБ", "Sunday": "ВС"
        }
        cur_day_ru = day_map.get(current_day, "")
        cur_time = now.strftime("%H:%M")

        rows = get_schedule()
        for r in rows:
            if r["day"] == cur_day_ru and r["time"] == cur_time:
                game = r["game"]
                if game not in active_games:
                    await bot.send_message(
                        GROUP_ID,
                        f"⏰ Время игры! Запускаю {game}..."
                    )
                    if game == "777":
                        await cmd_start777_fake()
                    elif game == "quiz":
                        await cmd_startquiz_fake()
                    elif game == "21":
                        await cmd_start21_fake()

        await asyncio.sleep(60)

async def cmd_start777_fake():
    active_games["777"] = {"players": [], "phase": "join"}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Участвовать", callback_data="join_777")]
    ])
    await bot.send_message(GROUP_ID,
        f"🎰 ЛУДКА ДО 777! (по расписанию)\n"
        f"🎁 Приз: {get_prize('777')}\n"
        f"Нажми кнопку. Набор: 2 минуты.", reply_markup=kb)
    await asyncio.sleep(120)
    await run_777(GROUP_ID)

async def cmd_startquiz_fake():
    active_games["quiz"] = {"players": [], "phase": "join", "scores": {}}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Участвовать", callback_data="join_quiz")]
    ])
    await bot.send_message(GROUP_ID,
        f"📚 ВИКТОРИНА! (по расписанию)\n"
        f"🎁 Приз: {get_prize('quiz')}\n"
        f"Нажми кнопку. Набор: 2 минуты.", reply_markup=kb)
    await asyncio.sleep(120)
    await run_quiz(GROUP_ID)

async def cmd_start21_fake():
    active_games["21"] = {"players": [], "phase": "join"}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Участвовать", callback_data="join_21")]
    ])
    await bot.send_message(GROUP_ID,
        f"🎲 ИГРА 21! (по расписанию)\n"
        f"🎁 Приз: {get_prize('21')}\n"
        f"Нажми кнопку. Набор: 2 минуты.", reply_markup=kb)
    await asyncio.sleep(120)
    await run_21(GROUP_ID)

# ============================================
# ЗАПУСК
# ============================================

async def main():
    init_db()
    print("✅ Бот запущен!")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
