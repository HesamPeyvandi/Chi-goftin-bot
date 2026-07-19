# Chi Goftin — Telegram Group Summarizer Bot

A Telegram bot that reads group chat activity and produces a short, natural-language
summary of what people were talking about, on demand via `/summarize`.

## How it works

1. The bot silently stores every text message sent in a group it's a member of.
2. When someone runs `/summarize [n]`, it pulls the last `n` stored messages
   (default 10) for that group and asks an AI model to turn them into a short,
   casual paragraph — never a bullet list, never a "key points" recap.
3. The summarization logic never runs locally: the bot only builds the prompt
   and hands it off to an AI provider. If the primary provider is rate-limited
   or errors out, the bot silently retries with the next one in the chain, so
   the end user never notices a provider switch.

   ### Language behavior

      Incoming messages can be in any language — Gemini, Grok, and the OpenRouter
      models are all multilingual, so the bot understands mixed-language group
      chats without any extra configuration.

      The **output summary is always in Persian**, regardless of the input
      language, because the summarization prompt explicitly instructs the model
      to write the recap in casual, conversational Persian and to transliterate
      non-Persian names into Persian script. To support a different output
      language, the prompt in `ai_provider.py` (`build_summary_prompt`) would need
      to be changed.

## Architecture

```
main.py           Entry point: starts the bot (polling) and a keep-alive web server
config.py         All environment variables and constants in one place
database.py       SQLite storage layer (groups + messages)
ai_provider.py     Gemini -> Grok -> OpenRouter fallback chain + the summarization prompt
handlers.py       Telegram command/message handlers
```

`openpyxl` is used only by the `/export` admin command to build the `.xlsx` file; everything else has no dependency on it.

### AI provider fallback chain

Requests are tried in this exact order, and the first one that succeeds wins:

1. **Gemini** (`google-generativeai`)
2. **Grok** (xAI, OpenAI-compatible endpoint)
3. **OpenRouter**, using `openrouter/free` by default — this is OpenRouter's
   auto-router, which picks whichever free model is currently available, so
   the bot keeps working even as OpenRouter's free-model catalog changes.
   You can pin a specific free model instead via the `OPENROUTER_MODEL` env
   var (check [openrouter.ai/models](https://openrouter.ai/models), filtered
   to free, for current options).

The summarization prompt itself is untouched from the original implementation
— only the delivery mechanism (which provider executes it) changed.

### Database

- `groups` table: one row per group, storing its title and whether the admin
  has marked it for **permanent** message retention.
- `messages` table: chat history, stored per group.
- Groups that are **not** marked permanent automatically get pruned down to
  the last `DEFAULT_MESSAGE_HISTORY_LIMIT` messages (default: 1500) every
  time a new message comes in. Groups marked permanent are never pruned.

### Admin commands

Only the Telegram user ID set in `ADMIN_USER_ID` can run these:

| Command | Description |
|---|---|
| `/groups` | Lists every group the bot has seen, with its `chat_id` and current retention status. |
| `/setpermanent <chat_id>` | Marks a group for permanent (unpruned) message storage. |
| `/removepermanent <chat_id>` | Reverts a group to the default, pruned retention policy. |
| `/export <chat_id>` | Exports every stored message for that group as an `.xlsx` file (columns: row, time, sender, forwarded-from, text) and sends it directly in the chat. |

Run `/groups` first to find a group's `chat_id`, then use it with the other commands. `/export` pulls the group's **full** history from the database — it isn't limited by `DEFAULT_MESSAGE_HISTORY_LIMIT` — so it's the only way to see everything currently stored, including for permanent groups.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```
   At minimum you need `TELEGRAM_BOT_TOKEN` and `ADMIN_USER_ID`. You don't need
   all three AI provider keys — any missing key is simply skipped in the
   fallback chain — but at least one is required for `/summarize` to work.
3. Run it:
   ```bash
   python main.py
   ```

## Deploying on a free server

This project ships with a tiny Flask endpoint (`/`) alongside the bot's
polling loop specifically so it can run on **Render's free web service tier**:

1. Push this repo to GitHub.
2. On [render.com](https://render.com), create a new **Web Service** from
   the repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `python main.py`
3. Add your environment variables (from `.env.example`) in Render's
   **Environment** tab.
4. Render's free tier spins the service down after ~15 minutes of no HTTP
   traffic, and takes ~30–60 seconds to spin back up on the next request.
   Since Telegram messages don't hit the web server directly, use a free
   uptime pinger like [UptimeRobot](https://uptimerobot.com) to hit your
   Render URL every 5–10 minutes and keep the bot process alive 24/7.

**Important caveat about SQLite on free tiers:** Render's free web services
use ephemeral disk — the SQLite file can be reset on redeploys or after
extended downtime. For a portfolio project or a small bot this is usually an
acceptable trade-off. If you need guaranteed persistence, either:
- upgrade to a Render plan with a persistent disk, or
- swap `database.py`'s connection for a free hosted database instead of a
  local file (e.g. [Turso](https://turso.tech), which is SQLite-compatible
  over the network and has a free tier) — the rest of the codebase wouldn't
  need to change, since all database access goes through `database.py`.

Alternative free hosts worth comparing if Render's spin-down behavior is a
problem for you: check current offerings, as free tiers change often.
