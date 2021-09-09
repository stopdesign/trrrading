import re
import asyncio
import logging
import settings
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiogram.utils.markdown import hpre
from exchange import BaseExchange
from stats import AccountStats

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


log = logging.getLogger("tg_bot")


TELEGRAM_TOKEN = getattr(settings, "TELEGRAM_TOKEN", None)
TELEGRAM_USERNAME = getattr(settings, "TELEGRAM_USERNAME", None)


class TelegramBotMixin:
    bot: Dispatcher
    exchange: BaseExchange
    account_stats: AccountStats

    async def tg_kill(self, message):
        if message.chat.username != TELEGRAM_USERNAME:
            return
        log.warning(f"Kill signal")
        await message.answer(f"STOP")
        await asyncio.sleep(2)  # чтобы сообщение отметилось как обработанное
        self.exchange.stop_listen()

    async def tg_info(self, message):
        log.info(f"Info requested")
        if message.chat.username != TELEGRAM_USERNAME:
            return
        txt = ansi_escape.sub("", self.account_stats.portfolio_info())
        await message.answer(f"{hpre(txt)}", parse_mode=ParseMode.HTML)

    def start_tg_bot(self):
        if not TELEGRAM_TOKEN:
            return
        log.info("Start bot")
        self.bot = Dispatcher(Bot(token=TELEGRAM_TOKEN))
        self.bot.register_message_handler(self.tg_kill, commands=['kill'])
        self.bot.register_message_handler(self.tg_info, commands=['info'])
        # self.dp.register_errors_handler
        asyncio.get_event_loop().create_task(self.bot.start_polling())

    def stop_tg_bot(self):
        if TELEGRAM_TOKEN and self.bot:
            log.info("Stop bot")
            self.bot.stop_polling()
