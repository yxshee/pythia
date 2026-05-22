"""Typed settings loaded from environment variables / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pythia runtime configuration.

    Values are loaded from environment variables, falling back to a .env file at the
    repo root. See ``.env.example`` for the full set of supported keys.
    """

    # Arc
    arc_rpc_url: str = "https://rpc.testnet.arc-node.thecanteenapp.com/v1/REPLACE_ME"
    arc_chain_id: int = 5042002
    private_key: str = "0x" + "0" * 64

    # Deployed contracts (see Deployments table in README)
    pythia_vault_address: str | None = None
    trace_log_address: str | None = None
    usdc_address_arc: str | None = None

    # Polymarket
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_builder_code: str | None = None
    polymarket_builder_fee_bps: int = 100

    # LLM keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Telegram
    telegram_bot_token: str | None = None
    telegram_channel_id: str | None = None

    # Trace storage
    irys_node_url: str = "https://node1.irys.xyz"
    irys_private_key: str | None = None

    # Other intel
    cambrian_api_key: str | None = None
    envio_hypersync_url: str = "https://arc.hypersync.xyz"

    # Operating params
    pythia_theme: str = Field(
        default="crypto",
        description=(
            "Polymarket Gamma tag slug (single-word) or a compound theme handled client-side. "
            "Single-word values are sent as `tag_slug`; compound themes (e.g. 'crypto-politics') "
            "fall back to no server-side filter and are matched on the payload's tags array."
        ),
    )
    pythia_paper_capital_usdc: float = Field(
        default=1000.0,
        description=(
            "Virtual capital used by the PortfolioManager to size hypothetical positions. "
            "Pythia never trades its own money; this is the notional balance for paper PnL."
        ),
    )
    pythia_max_position_usdc: float = 50.0
    pythia_daily_max_trades: int = 20
    pythia_dry_run: bool = Field(
        default=True,
        description=(
            "If True (default), picks are logged to console only. If False, the loop also pushes "
            "each pick to the Telegram channel via the bot's broadcast helper."
        ),
    )

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def load_settings() -> Settings:
    """Load and validate settings. Cached at the module level for callers who want a shared instance."""
    return Settings()


SETTINGS = load_settings()
