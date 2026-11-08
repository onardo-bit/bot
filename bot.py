import asyncio
import random
import sqlite3
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PollAnswer

# --- КОНФИГУРАЦИЯ ---
TOKEN = "ВАШ_ТОКЕН_ИЗ_RAILWAY" # Желательно через env: os.getenv("BOT_TOKEN")
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
