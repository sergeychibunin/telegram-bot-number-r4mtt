import logging

from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = ''  # TODO remove
PROXY_URL = 'socks5://50.205.119.150:32482'


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, proxy=PROXY_URL)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def echo(message: types.Message):
    await message.answer(message.text)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
