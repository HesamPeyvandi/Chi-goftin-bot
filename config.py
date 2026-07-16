"""
Centralized configuration for the bot.

All secrets and tunable values are read from environment variables so the
same codebase can run locally, in CI, or on any hosting provider without
code changes.
"""

import os


def _get_int_env(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to a default on error."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Telegram user ID of the bot administrator. Only this user can run
# admin-only commands such as /groups, /setpermanent and /removepermanent.
ADMIN_USER_ID = _get_int_env("ADMIN_USER_ID", 0)

# --- AI providers (used in this exact fallback order) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.1-flash-lite")

GROK_API_KEY = os.environ.get("GROK_API_KEY")
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-4.3")
GROK_BASE_URL = "https://api.x.ai/v1"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
# "openrouter/free" auto-selects an available free model, so the bot keeps
# working even if a specific free model is retired from the catalog.
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

AI_REQUEST_TIMEOUT_SECONDS = _get_int_env("AI_REQUEST_TIMEOUT_SECONDS", 60)

# --- Database ---
DATABASE_PATH = os.environ.get("DATABASE_PATH", "chi_goftin.db")

# Default number of messages kept per group that the admin has NOT marked
# for permanent storage. Older messages beyond this count are pruned.
DEFAULT_MESSAGE_HISTORY_LIMIT = _get_int_env("DEFAULT_MESSAGE_HISTORY_LIMIT", 1500)

# --- Web server (keep-alive endpoint for free hosting tiers) ---
PORT = _get_int_env("PORT", 10000)
