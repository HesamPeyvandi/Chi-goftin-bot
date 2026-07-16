"""
Telegram bot handlers.

- save_message: stores every incoming group message in the database.
- summarize_chat: builds the (unchanged) summarization prompt from stored
  history and delegates the actual summarization to ai_provider.
- Admin-only commands: /groups, /setpermanent, /removepermanent.
"""

import datetime
import logging

import telebot

import ai_provider
import config
import database as db

logger = logging.getLogger(__name__)

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

DEFAULT_SUMMARY_MESSAGE_COUNT = 10
GROUP_CHAT_TYPES = ("group", "supergroup")


def _is_admin(user_id: int) -> bool:
    return config.ADMIN_USER_ID != 0 and user_id == config.ADMIN_USER_ID


def _format_message(message: telebot.types.Message) -> str:
    user_name = message.from_user.first_name
    text = message.text
    message_time = datetime.datetime.fromtimestamp(message.date, tz=TEHRAN_TZ).strftime("%H:%M")

    forward_source = ""
    is_forwarded = False

    if message.forward_from_chat:
        forward_source = message.forward_from_chat.title
        is_forwarded = True
    elif message.forward_from:
        forward_source = message.forward_from.first_name
        is_forwarded = True
    elif message.forward_sender_name:
        forward_source = message.forward_sender_name
        is_forwarded = True

    if is_forwarded:
        return f"[ساعت {message_time} | {user_name} (فوروارد از {forward_source})]: {text}"
    return f"[ساعت {message_time} | {user_name}]: {text}"


def register_handlers(bot: telebot.TeleBot) -> None:
    @bot.message_handler(commands=["summarize"])
    def summarize_chat(message: telebot.types.Message):
        chat_id = message.chat.id

        if not db.has_messages(chat_id):
            bot.reply_to(message, "هنوز پیامی برای خلاصه کردن وجود نداره!")
            return

        try:
            command_parts = message.text.split()
            requested_count = (
                int(command_parts[1]) if len(command_parts) > 1 else DEFAULT_SUMMARY_MESSAGE_COUNT
            )
        except ValueError:
            requested_count = DEFAULT_SUMMARY_MESSAGE_COUNT

        messages_to_summarize = db.get_recent_messages(chat_id, requested_count)
        prompt = ai_provider.build_summary_prompt(messages_to_summarize)

        bot.reply_to(message, "در حال خوندن پیام‌ها... ⏳")

        try:
            summary_text = ai_provider.generate_summary(prompt)
            final_message = f"خلاصه ی پیام ها:\n\n{summary_text}"
            bot.reply_to(message, final_message)
        except Exception as error:
            bot.reply_to(message, "متاسفانه تو خلاصه‌سازی مشکلی پیش اومد.")
            logger.error("Summarization failed for chat %s: %s", chat_id, error)

    @bot.message_handler(commands=["groups"])
    def list_groups(message: telebot.types.Message):
        if not _is_admin(message.from_user.id):
            return

        groups = db.get_all_groups()
        if not groups:
            bot.reply_to(message, "هنوز هیچ گروهی ثبت نشده.")
            return

        lines = []
        for chat_id, title, is_permanent in groups:
            status = "دائمی" if is_permanent else "پیش‌فرض"
            lines.append(f"- {title} | {chat_id} | {status}")

        bot.reply_to(message, "\n".join(lines))

    @bot.message_handler(commands=["setpermanent"])
    def set_permanent(message: telebot.types.Message):
        if not _is_admin(message.from_user.id):
            return
        _handle_permanent_toggle(bot, message, is_permanent=True)

    @bot.message_handler(commands=["removepermanent"])
    def remove_permanent(message: telebot.types.Message):
        if not _is_admin(message.from_user.id):
            return
        _handle_permanent_toggle(bot, message, is_permanent=False)

    @bot.message_handler(func=lambda message: True)
    def save_message(message: telebot.types.Message):
        if message.chat.type not in GROUP_CHAT_TYPES:
            return
        if not message.text:
            return

        chat_id = message.chat.id
        db.upsert_group(chat_id, message.chat.title)

        formatted_message = _format_message(message)
        db.add_message(chat_id, formatted_message)


def _handle_permanent_toggle(bot: telebot.TeleBot, message: telebot.types.Message, is_permanent: bool) -> None:
    command_parts = message.text.split()
    if len(command_parts) < 2:
        bot.reply_to(message, "استفاده: /setpermanent <chat_id> یا /removepermanent <chat_id>")
        return

    try:
        chat_id = int(command_parts[1])
    except ValueError:
        bot.reply_to(message, "chat_id باید یک عدد باشه.")
        return

    updated = db.set_group_permanent(chat_id, is_permanent)
    if not updated:
        bot.reply_to(message, "این گروه هنوز شناخته نشده.")
        return

    status = "دائمی" if is_permanent else "پیش‌فرض"
    bot.reply_to(message, f"وضعیت ذخیره‌سازی گروه {chat_id} به «{status}» تغییر کرد.")
