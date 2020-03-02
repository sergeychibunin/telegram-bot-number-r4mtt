import logging
import argparse
import uuid
import pickle
import codecs
import aiosqlite
import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
from time import time
from ujson import decode
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from aiosqlite.core import Connection
from aiogram import Bot, Dispatcher, executor, types
from aiohttp import ClientSession
from os import unlink
from typing import Any, Dict

# Configure logging
logging.basicConfig(level=logging.INFO)

DB_PATH = 'db.sqlite'
EXCHANGE_API = 'https://api.exchangeratesapi.io'


class EAPINotAvailable(Exception):
    """The special exception for problems with the exchange service"""
    ...


def dt2str(dt: date) -> str:
    """Convert date object to string"""
    return dt.strftime('%Y-%m-%d')


def str2dt(_str: str) -> date:
    """Convert string to date object"""
    return datetime.strptime(_str, '%Y-%m-%d').date()


def round_cur(cur: Decimal) -> Decimal:
    """Round a decimal with two decimal precision"""
    return cur.quantize(Decimal('0.01'), ROUND_HALF_UP)


def conv_obj_str(obj: Any) -> str:
    """Convert any object to string"""
    return codecs.encode(pickle.dumps(obj), "base64").decode()


def conv_str_obj(_str: str) -> Any:
    """Convert string to any object"""
    return pickle.loads(codecs.decode(_str.encode(), "base64"))


async def query_ex_api(path: str = '') -> str:
    """Query something from exchange API by HTTP"""
    async with ClientSession() as session:
        async with session.get(f'{EXCHANGE_API}{path}') as resp:
            return await resp.text()


def storage() -> Connection:
    """Return a connection to sqlite3"""
    return aiosqlite.connect(DB_PATH)


def check_storage() -> None:
    """Check DB scheme or create one"""
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


async def update_cache(data: Any) -> None:
    """Update the cached value in the storage and save a timestamp"""
    async with storage() as db:
        await db.execute("UPDATE stat SET value = :data WHERE key = 'cache'",
                         {'data': conv_obj_str(data)})
        await db.execute("UPDATE stat SET value = :data WHERE key = 'last_request_at'",
                         {'data': str(int(time()))})
        await db.commit()


async def get_cache() -> Any:
    """Get the cached value from the storage"""
    cache = {}
    async with storage() as db:
        async with db.execute('SELECT key, value FROM stat') as cursor:
            async for row in cursor:
                cache[row[0]] = row[1]
    return cache


def parse_latest(raw_data: str) -> Dict[str, Decimal]:
    """Convert list of currencies with their values to dict object"""
    try:
        rates = decode(raw_data)['rates']
    except KeyError:
        raise EAPINotAvailable
    return {curr: round_cur(Decimal(rates[curr])) for curr in rates.keys()}


def format_latest(data: dict) -> str:
    """Format the user view for currency values"""
    return '\n'.join([f'{k}: {v}' for k, v in data.items()])


async def update_curr_info() -> Dict[str, Decimal]:
    """Query an info and save to cache"""
    stat_data_raw = await query_ex_api('/latest?base=USD')
    stat_data = parse_latest(stat_data_raw)
    await update_cache(stat_data)
    return stat_data


async def get_curr_info() -> Dict[str, Decimal]:
    """Get an info about currencies"""
    stat_data_cache = await get_cache()
    if not stat_data_cache['last_request_at'] \
            or (time() - int(stat_data_cache['last_request_at']) > 10 * 60):
        stat_data = await update_curr_info()
    else:
        stat_data = conv_str_obj(stat_data_cache['cache'])
    return stat_data


async def handle_lst() -> str:
    """Process the command /list|/lst.
    This is a handler
    """
    try:
        return format_latest(await get_curr_info())
    except EAPINotAvailable:
        return 'Exchange rate service is unavailable'


async def handle_exchange(message: types.Message) -> str:
    """Process the command /exchange.
    This is a handler
    """
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
                return 'The command is wrong'

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
        return 'The command is wrong'

    return f'{round_cur(cmd_sense[0] * stat_data[cmd_sense[2]])} {cmd_sense[2]}'  # TODO Is there a typo in TOR?


async def handle_history(message: types.Message) -> None:
    """Process the command /history.
    This is a handler
    """
    stat_data = await get_curr_info()
    cmd_parts = message.text.split(' ')
    cmd_sense = []
    for part in cmd_parts:
        if part == '/history':
            continue
        pair = part.split('/')
        if len(pair) == 2 and pair[1] in stat_data.keys():
            cmd_sense.append(pair[1])

    if len(cmd_sense) == 0 or f'/history USD/{cmd_sense[0]} for 7 days' != message.text:
        await message.answer('The command is wrong')
        return

    date_to = date.today()
    date_from = date_to - timedelta(7)

    query_text = (f'/history?'
                  f'start_at={dt2str(date_from)}&'
                  f'end_at={dt2str(date_to)}&'
                  f'base=USD&'
                  f'symbols={cmd_sense[0]}')

    h_data_raw = await query_ex_api(query_text)
    h_data = decode(h_data_raw)
    try:
        h_data['rates']
    except KeyError:
        await message.answer('No exchange rate data is available for the selected currency.')
        return

    # generate chart
    chart_data_x = sorted(h_data['rates'].keys(), key=lambda x: str2dt(x))  # dates
    chart_data_y = []  # currency values
    list(map(lambda x:
             chart_data_y.append(float(list(h_data['rates'][x].values())[0])),
             chart_data_x))
    chart_data_x = [str2dt(dt) for dt in chart_data_x]
    fig, ax = plt.subplots()
    ax.plot(chart_data_x, chart_data_y)
    ax.set(xlabel='days', ylabel=cmd_sense[0])
    plt.xticks(rotation=30)
    ax.grid()
    filename = str(uuid.uuid4())
    fig.savefig(filename)

    # send chart
    with open(f'{filename}.png', 'rb') as chart:
        await message.reply_photo(chart)

    # delete chart
    unlink(f'{filename}.png')

if __name__ == '__main__':
    # Configure system interface
    parser = argparse.ArgumentParser(description='Telegram change bot')
    parser.add_argument('--tg-bot-token', dest='tg_token', default='')
    parser.add_argument('--proxy', help='Anonymous HTTP/SOCKS5 proxy URL', default='')
    args = parser.parse_args()

    # Initialize bot and dispatcher
    bot = Bot(token=args.tg_token, proxy=args.proxy) if args.proxy else Bot(token=args.tg_token)
    dp = Dispatcher(bot)

    @dp.message_handler(commands=['list', 'lst'])
    async def lst(message: types.Message) -> None:
        """Process the command /list|/lst.
        Return list of all available rates
        """
        await message.answer(await handle_lst())


    @dp.message_handler(commands=['exchange'])
    async def exchange(message: types.Message) -> None:
        """Process the command /exchange.
        Convert to the second currency
        """
        await message.answer(await handle_exchange(message))


    @dp.message_handler(commands=['history'])
    async def history(message: types.Message) -> None:
        """Process the command /history.
        Return an image chart which shows the exchange rate chart of the selected currency for the last 7 days
        """
        await handle_history(message)


    @dp.message_handler(commands=['start'])
    async def echo(message: types.Message) -> None:
        """Process the command /start.
        Greet an user
        """
        await message.answer('Hey!')


    check_storage()
    executor.start_polling(dp, skip_updates=True)
