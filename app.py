import logging
import aiosqlite
import sqlite3
from ujson import decode
from decimal import Decimal, ROUND_HALF_UP
from aiogram import Bot, Dispatcher, executor, types
from aiohttp import ClientSession

API_TOKEN = '724686344:AAH-LQ1SLMrYHPHBQANj9CgiMU9ARS6Awpk'  # TODO reset TOKEN and remove from here
PROXY_URL = 'http://5.189.170.254:80'
DB_PATH = 'db.sqlite'
EXCHANGE_API = 'https://api.exchangeratesapi.io'


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, proxy=PROXY_URL) if PROXY_URL else Bot(token=API_TOKEN)
dp = Dispatcher(bot)


def round_cur(cur):
    return cur.quantize(Decimal('0.01'), ROUND_HALF_UP)


async def query_ex_api(path=''):
    async with ClientSession() as session:
        async with session.get(f'{EXCHANGE_API}{path}') as resp:
            return await resp.text()


def storage():
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


async def update_cache(data):
    async with storage() as db:
        await db.execute("UPDATE stat SET value = '{}' WHERE key = 'cache'", [data])
        await db.commit()


def parse_latest(raw_data):
    rates = decode(raw_data)['rates']  # todo api validation
    return {curr: round_cur(Decimal(rates[curr])) for curr in rates.keys()}


def format_latest(data):
    return '\n'.join([f'{k}{v}' for k, v in data.items()])


@dp.message_handler(commands=['list', 'lst'])
async def lst(message: types.Message):
    stat_data_raw = await query_ex_api('/latest?base=USD')
    stat_data = parse_latest(stat_data_raw)
    await update_cache(stat_data)
    stat_data_fmt = format_latest(stat_data)
    await message.answer(stat_data_fmt)


@dp.message_handler(commands=['start'])
async def echo(message: types.Message):
    await message.answer('Hey!')


if __name__ == '__main__':
    check_storage()
    executor.start_polling(dp, skip_updates=True)
