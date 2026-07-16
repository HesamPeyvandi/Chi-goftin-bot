"""
Entry point.

Runs the Telegram bot on a background thread (long-polling) and a tiny
Flask web server on the main thread. The web server exists purely so free
hosting tiers that expect an HTTP port (e.g. Render) see the service as
"up" and can be kept awake by an external uptime pinger.
"""

import logging
import threading

import telebot
from flask import Flask

import config
import database as db
from handlers import register_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN)
register_handlers(bot)

app = Flask(__name__)


@app.route("/")
def health_check():
    return "Bot is running."


def run_bot() -> None:
    logger.info("Starting Telegram bot polling...")
    bot.infinity_polling()


if __name__ == "__main__":
    db.init_db()

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    app.run(host="0.0.0.0", port=config.PORT)
