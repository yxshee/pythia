"""Telegram bot - run with ``pythia-bot run`` after exporting TELEGRAM_BOT_TOKEN.

Subcommands:
  - run           : long-running bot. Handles /start, /status, /latest.
  - broadcast PATH: read a trace JSON file (as written by the agent's TracePublisher),
                    format it, and post to the configured channel.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

log = structlog.get_logger(__name__)


class BotSettings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    pythia_vault_address: str | None = None

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def _settings() -> BotSettings:
    s = BotSettings()
    if not s.telegram_bot_token:
        click.echo("TELEGRAM_BOT_TOKEN is required. Set it in .env or env.", err=True)
        sys.exit(1)
    return s


# ----------------------------------------------------------------------
#  Command handlers
# ----------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "*Pythia* - autonomous prediction-market reasoning agent\n\n"
        "I post every pick I make along with the full reasoning trace.\n"
        "Each decision is logged on Arc; each trace is pinned to IPFS.\n\n"
        "Commands:\n"
        "  /status  - show the live vault NAV + pick count\n"
        "  /latest  - show the most recent pick\n"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s: BotSettings = context.bot_data["settings"]
    traces_dir = _traces_dir()
    pick_count = len(list(traces_dir.glob("trace-*.json"))) if traces_dir.exists() else 0
    vault = s.pythia_vault_address or "(not deployed yet)"
    msg = (
        f"*Pythia status*\n"
        f"Vault on Arc: `{vault}`\n"
        f"Picks published: *{pick_count}*\n"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    traces_dir = _traces_dir()
    files = sorted(traces_dir.glob("trace-*.json")) if traces_dir.exists() else []
    if not files:
        if update.message:
            await update.message.reply_text("No picks yet. Pythia warms up at first cycle.")
        return
    latest = files[-1]
    payload = json.loads(latest.read_text())
    text = _format_pick(payload)
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


# ----------------------------------------------------------------------
#  Broadcast helper - used by the agent loop or run manually
# ----------------------------------------------------------------------
async def broadcast_trace(settings: BotSettings, trace_path: Path) -> None:
    from telegram import Bot

    payload = json.loads(trace_path.read_text())
    text = _format_pick(payload)
    bot = Bot(token=settings.telegram_bot_token)
    await bot.send_message(
        chat_id=settings.telegram_channel_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )
    log.info("broadcast.sent", trace=trace_path.name, chat=settings.telegram_channel_id)


def _format_pick(payload: dict[str, Any]) -> str:
    """Telegram broadcast formatter. Preview-only - never leak gated fields."""
    preview = payload.get("preview") or {}
    publication = payload.get("publication") or {}
    builder_code = payload.get("builder_code", "pythia")
    site = _agora_site_url()

    trace_id = preview.get("trace_id") or payload.get("trace_id", "?")
    decision = preview.get("decision", "HOLD")
    question = preview.get("question") or "(unnamed market)"
    market_id = (preview.get("market_id") or "")[:14]
    confidence = preview.get("confidence", "?")
    risk = preview.get("risk", "?")
    implied = preview.get("current_implied_yes", 0.0)
    agent_p = preview.get("agent_probability_yes", 0.0)
    model = preview.get("model", "?")
    trace_hash = preview.get("trace_hash", "")
    unlock_url = f"{site}/pick/{trace_id}"

    polymarket_link = publication.get("builder_code_link") or publication.get("fallback_link")
    polymarket_line = (
        f"\nView on Polymarket -> [{polymarket_link}]({polymarket_link})" if polymarket_link else ""
    )

    return (
        f"*Agora Alpha pick #{trace_id}*  ({model})\n"
        f"`{market_id}`  *{decision}* / *{confidence}* conf / *{risk}* risk\n"
        f"_{question[:140]}_\n\n"
        f"Market implied: *{implied:.1%}*  |  Agent fair: *{agent_p:.1%}*\n"
        f"Arc trace: `{trace_hash[:14]}`...{polymarket_line}\n\n"
        f"*Unlock full reasoning + suggested size + risk factors* -> [{unlock_url}]({unlock_url})\n"
        f"_USDC payment on Arc, builder code `{builder_code}`._"
    )


def _agora_site_url() -> str:
    """Public URL of the Agora Alpha web app. Overridable via env."""
    import os

    return os.environ.get("AGORA_SITE_URL", "https://agoraalpha.vercel.app")


def _traces_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "traces"


# ----------------------------------------------------------------------
#  CLI
# ----------------------------------------------------------------------
@click.group()
def cli() -> None:
    """Pythia Telegram bot."""


@cli.command("run")
def run_cmd() -> None:
    """Start the long-running bot. Handles commands; ready for broadcasts."""
    s = _settings()
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

    app = Application.builder().token(s.telegram_bot_token).build()
    app.bot_data["settings"] = s
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("latest", cmd_latest))

    click.echo("Pythia bot running. Press Ctrl-C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


@cli.command("broadcast")
@click.argument("trace_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def broadcast_cmd(trace_path: Path) -> None:
    """Post one trace JSON file to the configured channel."""
    s = _settings()
    if not s.telegram_channel_id:
        click.echo("TELEGRAM_CHANNEL_ID is required for broadcast.", err=True)
        sys.exit(1)
    asyncio.run(broadcast_trace(s, trace_path))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
