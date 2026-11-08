import os
import asyncio
import random
import sqlite3
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PollAnswer, ChatPermissions

# --- КОНФИГУРАЦИЯ ---
# Токен забирается из настроек Railway (Variables -> BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [7004839619]
ADMIN_USERNAME = "onardo-bit"
GROUP_ID = -5370978242
EXACT_777_VALUE = 64 # Значение диска 🎰 для 777

if not TOKEN:
    print("⚠️ ОШИБКА: Переменная BOT_TOKEN не установлена в Railway!")

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

reg_users = []  
quiz_scores = {} 

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

# --- АДМИН-КОМАНДЫ ---
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
            await message.answer("❌ Время от 10 до 1800 секунд.")
    except Exception:
        await message.answer("Формат: `/jointime 300`")

@dp.message(Command("prize"))
async def set_prize(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Формат: `/prize 777 1000 рублей` (игры: 777, quiz, 21)")
        return
    game, text = args[1].lower(), args[2]
    if game not in ["777", "quiz", "21"]:
        await message.answer("❌ Допустимые игры: 777, quiz, 21")
        return
    cur.execute("INSERT OR REPLACE INTO prizes (game, text) VALUES (?, ?)", (game, text))
    db.commit()
    await message.answer(f"✅ Приз для **{game}** сохранен: {text}")

@dp.message(Command("prizes"))
async def show_prizes(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    cur.execute("SELECT game, text FROM prizes")
    rows = cur.fetchall()
    if not rows:
        await message.answer("🎁 Призы не настроены.")
        return
    res = "🎁 **Призы:**\n" + "\n".join([f"• {g.upper()}: {t}" for g, t in rows])
    await message.answer(res)

@dp.message(Command("mute"))
async def mute_chat(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    try:
        await bot.set_chat_permissions(GROUP_ID, ChatPermissions(can_send_messages=False))
        await bot.send_message(GROUP_ID, "🔇 Чат переведён в режим «Только чтение».")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

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
        await message.answer(f"Ошибка: {e}")

# --- ИГРА 1: 777 ---
@dp.message(Command("start777"))
async def start_777(message: types.Message):
    global game_777_active
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    game_777_active = True
    await bot.send_message(
        GROUP_ID,
        "🎰 **ИГРА «ЛУДКА 777» НАЧАЛАСЬ!**\n\n"
        "Отправляйте эмодзи 🎰 со своей клавиатуры в чат.\n"
        "Кто первым выбьет 7️⃣7️⃣7️⃣ — тот победил!"
    )

@dp.message(F.dice.emoji == "🎰")
async def check_777_roll(message: types.Message):
    global game_777_active
    if not game_777_active or message.chat.id != GROUP_ID:
        return

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
            f"Для получения приза напишите @{ADMIN_USERNAME}"
        )

# --- ИГРА 2: ИГРА 21 ---
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
        f"🎲 **РЕГИСТРАЦИЯ НА ИГРУ «21»**\n\n"
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

    players_queue = []
    for uid in reg_users:
        cur.execute("SELECT username FROM users WHERE id=?", (uid,))
        res = cur.fetchone()
        un = res[0] if res else None
        players_queue.append({"id": uid, "un": un, "score": 0, "busts": 0})

    initial_players = [dict(p) for p in players_queue]
    winner = None

    await bot.send_message(
        GROUP_ID,
        f"🚀 **Игра «21» стартует!** Участников: {len(players_queue)}\n"
        f"⚙️ Бот крутит кубик 🎲 за каждого по очереди."
    )

    while game_21_active and not winner:
        if not players_queue:
            await bot.send_message(GROUP_ID, "🔄 Все игроки выбыли! Перезапуск раунда...")
            players_queue = [dict(p) for p in initial_players]
            for p in players_queue:
                p["score"] = 0
                p["busts"] = 0
            continue

        player = players_queue.pop(0)
        mention = get_mention(player["id"], player["un"])

        await bot.send_message(GROUP_ID, f"🎲 Ход игрока {mention} (Сумма: {player['score']})")
        
        dice_msg = await bot.send_dice(GROUP_ID, emoji="🎲")
        val = dice_msg.dice.value
        player["score"] += val

        await asyncio.sleep(1.5)

        await bot.send_message(GROUP_ID, f"{mention}: 🎲 Выпало **{val}** | Сумма: **{player['score']}**")

        if player["score"] == 21:
            winner = player
            break
        elif player["score"] > 21:
            if player["busts"] == 0:
                player["busts"] = 1
                player["score"] = 0
                players_queue.append(player)
                await bot.send_message(GROUP_ID, f"💥 {mention} превысил 21! Сумма сброшена на 0, уходит в конец очереди.")
            else:
                await bot.send_message(GROUP_ID, f"❌ {mention} снова превысил 21 и выбывает!")
        else:
            players_queue.append(player)

        await asyncio.sleep(2.0)

    if winner:
        game_21_active = False
        cur.execute("SELECT text FROM prizes WHERE game='21'")
        pz = cur.fetchone()
        prize_text = pz[0] if pz else "Не указан"

        await bot.send_message(
            GROUP_ID,
            f"🏆 **ПОБЕДИТЕЛЬ В 21:** {get_mention(winner['id'], winner['un'])}\n"
            f"🎯 Набрал ровно **21**!\n"
            f"🎁 Приз: {prize_text}\n\n"
            f"Напишите @{ADMIN_USERNAME} для получения приза!"
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
        f"5 вопросов. Время на регистрацию: **{join_time} сек.**",
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

    if not quiz_scores:
        await bot.send_message(GROUP_ID, "Викторина завершена. Ответы не получены.")
        game_quiz_active = False
        return

    sorted_players = sorted(quiz_scores.items(), key=lambda x: (-x[1]["score"], x[1]["last_ts"]))
    win_id, win_data = sorted_players[0]

    cur.execute("SELECT text FROM prizes WHERE game='quiz'")
    pz = cur.fetchone()
    prize_text = pz[0] if pz else "Не указан"

    await bot.send_message(
        GROUP_ID,
        f"🏆 **ПОБЕДИТЕЛЬ ВИКТОРИНЫ:** {get_mention(win_id, win_data['username'])}\n"
        f"📊 Очки: **{win_data['score']}**\n"
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

# --- СТАРТ ---
async def main():
    if not bot:
        return
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
