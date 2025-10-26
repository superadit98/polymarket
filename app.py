"""Entrypoint for the Polymarket smart money Telegram bot."""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable, List, MutableMapping, Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from services.nansen import is_smart_money
from services.polymarket import query_trades
from utils.fmt import build_message

# ---- logging ----
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROXY_ENV_VARS = (
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"
)

def strip_proxy_variables(env: MutableMapping[str, str],
                          keys: Iterable[str] = PROXY_ENV_VARS) -> None:
    """Remove known proxy env variables that sering bikin Telegram ke-block."""
    for key in keys:
        if key in env:
            logger.info("Removing proxy environment variable: %s", key)
            env.pop(key, None)

def load_config() -> None:
    load_dotenv()

def get_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Halo! Aku bot Smart Money untuk Polymarket.\n"
        "Ketik /smartmoney untuk melihat taruhan terbaru dari alamat berlabel Smart Money."
    )

async def smartmoney_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    try:
        trades = query_trades()
    except Exception as exc:
        logger.exception("Failed to fetch trades: %s", exc)
        await message.reply_text("Maaf, tidak bisa mengambil data Polymarket sekarang. Coba lagi nanti.")
        return

    smart_trades: list[dict[str, Any]] = []
    for trade in trades:
        maker = trade.get("makerAddress")
        if not maker:
            continue
        try:
            smart, labels = is_smart_money(maker)
        except Exception as exc:
            logger.exception("Failed to fetch labels for %s: %s", maker, exc)
            continue
        if smart:
            smart_trades.append({**trade, "labels": labels})

    context.user_data["smart_trades"] = smart_trades
    await _send_trade_message(message.chat_id, context, smart_trades, None)

async def _send_trade_message(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    trades: List[dict[str, Any]],
    outcome_filter: Optional[str],
) -> None:
    text = build_message(trades, outcome_filter)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("YES", callback_data="filter:YES"),
             InlineKeyboardButton("NO", callback_data="filter:NO")],
            [InlineKeyboardButton("REFRESH", callback_data="filter:REFRESH")],
        ]
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

async def filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    _, _, action = data.partition(":")

    if action == "REFRESH":
        try:
            trades = query_trades()
        except Exception as exc:
            logger.exception("Failed to refresh trades: %s", exc)
            await query.edit_message_text("Gagal memuat ulang data Polymarket. Silakan coba lagi nanti.")
            return

        smart_trades: list[dict[str, Any]] = []
        for t in trades:
            maker = t.get("makerAddress")
            if not maker:
                continue
            try:
                smart, labels = is_smart_money(maker)
            except Exception as exc:
                logger.exception("Failed to fetch labels for %s: %s", maker, exc)
                continue
            if smart:
                smart_trades.append({**t, "labels": labels})
        context.user_data["smart_trades"] = smart_trades
        outcome_filter = None
    else:
        smart_trades = context.user_data.get("smart_trades") or []
        if not isinstance(smart_trades, list):
            smart_trades = []
        outcome_filter = action if action in {"YES", "NO"} else None

    text = build_message(smart_trades, outcome_filter)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("YES", callback_data="filter:YES"),
             InlineKeyboardButton("NO", callback_data="filter:NO")],
            [InlineKeyboardButton("REFRESH", callback_data="filter:REFRESH")],
        ]
    )
    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

def build_request() -> HTTPXRequest:
    """Buat HTTPXRequest. Jika ada TELEGRAM_PROXY, gunakan; kalau tidak, direct."""
    proxy_url = os.getenv("TELEGRAM_PROXY")
    if proxy_url:
        logger.info("Using Telegram proxy: %s", proxy_url)
        return HTTPXRequest(proxy=proxy_url)
    return HTTPXRequest()

def main() -> None:
    load_config()
    token = get_token()
    strip_proxy_variables(os.environ)  # aman buat Crostini/lingkungan yang nyuntik proxy

    request = build_request()
    application = Application.builder().token(token).request(request).build()

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("smartmoney", smartmoney_handler))
    application.add_handler(CallbackQueryHandler(filter_callback, pattern=r"^filter:"))

    logger.info("Starting bot polling loop")
    application.run_polling()

if __name__ == "__main__":
    main()
import os

def main():
    # Jalankan bot di sini
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    role = os.getenv("ROLE", "worker")
    if role == "worker":
        main()
