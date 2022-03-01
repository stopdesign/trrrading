import math
import re
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiogram.utils.markdown import hpre
from exchange import BaseExchange
from stats import AccountStats
from django.conf import settings

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

    async def tg_acc(self, message):
        log.info(f"Account info requested")
        if message.chat.username != TELEGRAM_USERNAME:
            return

        bot_margin = self.account_stats.get_margin_used_by_bot()

        txt = (
            f"Net Value:   {self.exchange.net_value:6.0f}\n"
            f"Margin Used: {bot_margin:6.0f}\n"
        )

        if hasattr(self.exchange, "real_margin"):
            txt += f"Margin Real: {self.exchange.real_margin:6.0f}\n"

        await message.answer(f"{hpre(txt)}", parse_mode=ParseMode.HTML)

    async def tg_info(self, message):
        log.info(f"Positions info requested")
        if message.chat.username != TELEGRAM_USERNAME:
            return

        txt_1 = ""
        txt_2 = ""

        positions = self.account_stats.positions_extra()

        total_pnl = 0
        bot_margin = self.account_stats.get_margin_used_by_bot()

        for symbol, position in sorted(positions.items()):
            ticker = symbol.split(".")[0]
            amount = position["amount"] or float("nan")
            advised = position["advised"] or float("nan")
            pnl = position["daily_pnl"] or float("nan")
            total_pnl += 0 if math.isnan(pnl) else pnl
            txt_2 += f"{ticker:<4}{amount:+8.0f}{advised:+8.0f}{pnl:+8.0f}\n"

        txt_1 += f"Net Value       {self.exchange.net_value:12.2f}\n"
        txt_1 += f"Daily PnL       {total_pnl:+12.2f}　　　　　　　　\n"
        txt_1 += f"Bot Margin      {bot_margin:12.2f}\n"
        if hasattr(self.exchange, "real_margin"):
            txt_1 += f"Real Margin     {self.exchange.real_margin:12.2f}\n"

        txt_1 += "\n         Pos     Adv     PnL\n"
        txt_1 += "————————————————————————————\n"
        txt_1 += txt_2

        txt = txt_1.replace("+nan", "   ·").replace(" nan", "   ·")
        txt = txt.replace(" ", " ")

        await message.answer(f"{hpre(txt)}", parse_mode=ParseMode.HTML)

    def start_tg_bot(self):
        if not TELEGRAM_TOKEN:
            return
        log.info("Start bot")
        self.bot = Dispatcher(Bot(token=TELEGRAM_TOKEN))
        self.bot.register_message_handler(self.tg_kill, commands=['kill'])
        self.bot.register_message_handler(self.tg_info, commands=['info'])
        self.bot.register_message_handler(self.tg_acc, commands=['acc'])
        # self.dp.register_errors_handler
        asyncio.get_event_loop().create_task(self.bot.start_polling())

    def stop_tg_bot(self):
        if TELEGRAM_TOKEN and self.bot:
            log.info("Stop bot")
            self.bot.stop_polling()
