"""Entrypoint for the Polymarket smart money Telegram bot."""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable, List, MutableMapping, Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from services.nansen import is_smart_money
from services.polymarket import query_trades
from utils.fmt import build_message

# Configure logging early so importers see it.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PROXY_ENV_VARS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)


def strip_proxy_variables(
    env: MutableMapping[str, str],
    keys: Iterable[str] = PROXY_ENV_VARS,
) -> None:
    """Remove known proxy environment variables.

    Crostini-based environments often inject proxy variables automatically.
    They break direct access to Telegram, so we eagerly remove them before
    constructing the HTTP client.  Accepting the mapping and list of keys makes
    this function easy to test.
    """

    for key in keys:
        if key in env:
            logger.info("Removing proxy environment variable: %s", key)
            env.pop(key, None)


def load_config() -> None:
    """Load environment variables from a .env file if present."""
    load_dotenv()


def get_token() -> str:
    """Fetch the Telegram bot token from the environment."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command with a short greeting."""
    if not update.message:
        return
    greeting = (
        "Halo! Aku bot Smart Money untuk Polymarket.\n"
        "Ketik /smartmoney untuk melihat taruhan terbaru dari alamat dengan label Smart Money."
    )
    await update.message.reply_text(greeting)


async def smartmoney_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /smartmoney command by fetching and displaying trades."""
    message = update.message
    if not message:
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    try:
        trades = query_trades()
    except Exception as exc:  # noqa: BLE001 - we handle and log the error for the user
        logger.exception("Failed to fetch trades: %s", exc)
        await message.reply_text(
            "Maaf, tidak bisa mengambil data Polymarket sekarang. Coba lagi nanti."
        )
        return

    smart_trades = []
    for trade in trades:
        maker = trade.get("makerAddress")
        if not maker:
            continue
        try:
            smart, labels = is_smart_money(maker)
        except Exception as exc:  # noqa: BLE001
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
    """Render and send a trade message with inline filtering buttons."""
    text = build_message(trades, outcome_filter)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("YES", callback_data="filter:YES"),
                InlineKeyboardButton("NO", callback_data="filter:NO"),
            ],
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
    """Handle inline button presses to filter or refresh trade data."""
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    _, _, action = data.partition(":")

    smart_trades: List[dict[str, Any]]
    if action == "REFRESH":
        try:
            trades = query_trades()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to refresh trades: %s", exc)
            await query.edit_message_text(
                "Gagal memuat ulang data Polymarket. Silakan coba lagi nanti."
            )
            return

        smart_trades = []
        for trade in trades:
            maker = trade.get("makerAddress")
            if not maker:
                continue
            try:
                smart, labels = is_smart_money(maker)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to fetch labels for %s: %s", maker, exc)
                continue
            if smart:
                smart_trades.append({**trade, "labels": labels})
        context.user_data["smart_trades"] = smart_trades
        outcome_filter = None
    else:
        cached = context.user_data.get("smart_trades")
        if isinstance(cached, list):
            smart_trades = cached
        else:
            try:
                trades = query_trades()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to refresh trades: %s", exc)
                await query.edit_message_text(
                    "Gagal memuat ulang data Polymarket. Silakan coba lagi nanti."
                )
                return

            smart_trades = []
            for trade in trades:
                maker = trade.get("makerAddress")
                if not maker:
                    continue
                try:
                    smart, labels = is_smart_money(maker)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to fetch labels for %s: %s", maker, exc)
                    continue
                if smart:
                    smart_trades.append({**trade, "labels": labels})
            context.user_data["smart_trades"] = smart_trades

        outcome_filter = action if action in {"YES", "NO"} else None

    text = build_message(smart_trades, outcome_filter)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("YES", callback_data="filter:YES"),
                InlineKeyboardButton("NO", callback_data="filter:NO"),
            ],
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
    """Create an HTTPXRequest that optionally routes traffic via TELEGRAM_PROXY."""
    request_kwargs: dict[str, Any] = {"trust_env": False}
    proxy_url = os.getenv("TELEGRAM_PROXY")
    if proxy_url:
        logger.info("Using Telegram proxy: %s", proxy_url)
        request_kwargs["proxy"] = proxy_url
    return HTTPXRequest(**request_kwargs)


def main() -> None:
    """Run the Telegram bot using long polling."""
    load_config()
    token = get_token()
    strip_proxy_variables(os.environ)

    request = build_request()
    application = (
        Application.builder()
        .token(token)
        .request(request)
        .build()
    )

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("smartmoney", smartmoney_handler))
    application.add_handler(CallbackQueryHandler(filter_callback, pattern=r"^filter:"))

    logger.info("Starting bot polling loop")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
