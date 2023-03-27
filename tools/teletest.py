# import telegram
# import socket
# from telegram.ext import Updater, CommandHandler

#!/usr/bin/env python
# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""


TOKEN = "2009157356:AAGIQcY00qSWbNEfaUNTID8ZChJ4evfMs8U"

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update


from telegram import __version__ as TG_VER

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

import socket


def vnc_status():
    status = "NOTHING"

    # Create a socket object
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0) # Set socket timeout to 3 seconds

    try:
        # Connect to VNC on port 5900
        sock.connect(('10.0.10.1', 5900))

        # Send 'RFB' string
        # sock.sendall(b'RFB')

        # Receive response
        response = sock.recv(1024).decode('utf-8')

        # Check if response is 'RFB'
        if 'RFB' in response:
            status = 'VNC is listening on port 5900'
        else:
            status = 'VNC is not responding correctly'

    except Exception as e:
        status = f'Error: {e}'
    finally:
        sock.close()

    return status

# Define a few command handlers. These usually take the two arguments update and
# context.
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Send a message when the command /start is issued."""
#     user = update.effective_user
#     await update.message.reply_html(
#         rf"Hi {user.mention_html()}!",
#         reply_markup=ForceReply(selective=True),
#     )
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with three inline buttons attached."""
    keyboard = [
        [
            InlineKeyboardButton("Option 1", callback_data="1"),
            InlineKeyboardButton("Option 2", callback_data="2"),
        ],
        [InlineKeyboardButton("Option 3", callback_data="3")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Please choose:", reply_markup=reply_markup)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    await query.edit_message_text(text=f"Selected option: {query.data}")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    status = vnc_status()

    # Send VNC status message to Telegram
    await update.message.reply_text(status)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Yelp!")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(CommandHandler("test", test_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()



# from telethon import TelegramClient, events

# client = TelegramClient('anon', 23689087, 'febfd720a4e3ac50d822a9f4083fd1b2')
# bot = client.start(bot_token=TOKEN)

# @bot.on(events.NewMessage(pattern='/start'))
# async def send_welcome(event):
#     await event.reply('Howdy, how are you doing?')

# @bot.on(events.NewMessage(pattern='/test'))
# async def send_test(event):

#     me = await bot.get_me()
#     print(me)
#     print()

#     # # You can send messages to yourself...
#     await client.send_message('stopdesign', 'Hello, myself!')

#     # # ...to some chat ID
#     # await client.send_message(-2009157356, 'Hello, group!')

#     # # ...to your contacts
#     # await client.send_message('+34600123123', 'Hello, friend!')

#     # ...or even to any username
#     # await client.send_message('vysochina', 'Testing Telethon!')

#     # await event.reply('Howdy, how are you doing?')

# # @bot.on(events.NewMessage)
# # async def echo_all(event):
# #     await event.reply(event.text)



if __name__ == "__main__":
    # client.loop.run_until_complete(client.send_message('vysochina', 'Hello, Telethon!'))
    # bot.run_until_disconnected()
    main()