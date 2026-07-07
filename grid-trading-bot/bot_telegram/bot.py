"""Telegram bot application wiring: builds the Application, registers all
handlers, and exposes `BotAppContext` that every handler uses to reach the
shared engine components (DCA manager, repos, risk manager, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass

from telegram import Update
from telegram.ext import Application, ContextTypes

from bot_telegram.conversations import build_newgrid_conversation
from bot_telegram.handlers import register_handlers
from config.settings import Settings
from exchange.base import ExchangeClient
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.repositories import Repositories
from trading.alert_manager import AlertManager
from trading.dca_manager import DCAManager
from utils.logger import get_logger

log = get_logger("telegram")


@dataclass
class BotAppContext:
    settings: Settings
    repos: Repositories
    exchange: ExchangeClient
    dca_manager: DCAManager
    risk_manager: RiskManager
    notifier: Notifier
    alert_manager: AlertManager

    def is_authorized(self, user_id: int) -> bool:
        return self.settings.is_authorized(user_id)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled Telegram error: %s", context.error, exc_info=context.error)


def build_application(app_context: BotAppContext) -> Application:
    application = (
        Application.builder()
        .token(app_context.settings.telegram_bot_token)
        .build()
    )

    application.add_handler(build_newgrid_conversation(app_context))
    register_handlers(application, app_context)
    application.add_error_handler(_on_error)

    log.info("Telegram application built and handlers registered")
    return application
