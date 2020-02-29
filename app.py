import logging
import pickle
import codecs
import aiosqlite
import sqlite3
from time import time
from ujson import decode
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from aiogram import Bot, Dispatcher, executor, types
from aiohttp import ClientSession
# TODO comments
API_TOKEN = ''  # TODO reset TOKEN and remove from here
PROXY_URL = ''
DB_PATH = 'db.sqlite'
EXCHANGE_API = 'https://api.exchangeratesapi.io'


# Configure logging
logging.basicConfig(level=logging.INFO)  # TODO

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, proxy=PROXY_URL) if PROXY_URL else Bot(token=API_TOKEN)
dp = Dispatcher(bot)


def round_cur(cur):
    return cur.quantize(Decimal('0.01'), ROUND_HALF_UP)


def conv_obj_str(obj):
    return codecs.encode(pickle.dumps(obj), "base64").decode()


def conv_str_obj(_str):
    return pickle.loads(codecs.decode(_str.encode(), "base64"))


async def query_ex_api(path=''):
    async with ClientSession() as session:
        async with session.get(f'{EXCHANGE_API}{path}') as resp:
            return await resp.text()


def storage():
    # todo query pool?
    return aiosqlite.connect(DB_PATH)


def check_storage():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute('SELECT key FROM stat')
    except sqlite3.OperationalError:
        cur.execute('CREATE TABLE stat (key text, value text)')
        cur.execute("INSERT INTO stat VALUES ('cache', '')")
        cur.execute("INSERT INTO stat VALUES ('last_request_at', '')")
        conn.commit()
        conn.close()


async def update_cache(data):
    async with storage() as db:
        await db.execute("UPDATE stat SET value = :data WHERE key = 'cache'",
                         {'data': str(conv_obj_str(data))})
        await db.execute("UPDATE stat SET value = :data WHERE key = 'last_request_at'",
                         {'data': str(int(time()))})
        await db.commit()


async def get_cache():
    cache = {}
    async with storage() as db:
        async with db.execute('SELECT key, value FROM stat') as cursor:
            async for row in cursor:
                cache[row[0]] = row[1]
    return cache


def parse_latest(raw_data):
    rates = decode(raw_data)['rates']  # todo api validation
    return {curr: round_cur(Decimal(rates[curr])) for curr in rates.keys()}


def format_latest(data):
    return '\n'.join([f'{k}: {v}' for k, v in data.items()])


async def update_curr_info():
    stat_data_raw = await query_ex_api('/latest?base=USD')
    stat_data = parse_latest(stat_data_raw)
    await update_cache(stat_data)
    return stat_data


async def get_curr_info():
    stat_data_cache = await get_cache()
    if not stat_data_cache['last_request_at'] \
            or (time() - int(stat_data_cache['last_request_at']) > 10 * 60):  # todo 10 * 60
        stat_data = await update_curr_info()
    else:
        stat_data = conv_str_obj(stat_data_cache['cache'])
    return stat_data


@dp.message_handler(commands=['list', 'lst'])
async def lst(message: types.Message):
    stat_data = await get_curr_info()
    stat_data_fmt = format_latest(stat_data)
    await message.answer(stat_data_fmt)


@dp.message_handler(commands=['exchange'])
async def exchange(message: types.Message):
    stat_data = await get_curr_info()
    cmd_parts = message.text.split(' ')
    cmd_sense = []
    for part in cmd_parts:
        if not part:
            continue

        if part.startswith('$'):
            try:
                cmd_sense.append(Decimal(part[1:]))
                cmd_sense.append('USD')
                continue
            except InvalidOperation:
                await message.answer('The command is wrong')
                return

        if part in stat_data.keys():
            cmd_sense.append(part)
            continue

        try:
            cmd_sense.append(Decimal(part))
        except InvalidOperation:
            continue

    if len(cmd_sense) != 3 \
            or not isinstance(cmd_sense[0], Decimal) \
            or cmd_sense[1] != 'USD':
        await message.answer('The command is wrong')
        return

    await message.answer(f'{round_cur(cmd_sense[0] * stat_data[cmd_sense[2]])} {cmd_sense[2]}')  # TODO a typo?


@dp.message_handler(commands=['start'])
async def echo(message: types.Message):
    await message.answer('Hey!')


if __name__ == '__main__':
    check_storage()
    executor.start_polling(dp, skip_updates=True)
