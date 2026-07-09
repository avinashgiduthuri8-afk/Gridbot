# Manual Grid Trading Bot for CoinDCX

A production-ready Python bot that runs manual grid trading strategies on [CoinDCX](https://coindcx.com), controlled entirely through Telegram. There is no web UI — all interaction happens via Telegram commands.

## What this bot does

- You send `/startgrid` in Telegram and walk through a guided setup: choose a coin, set a price range and grid count, specify investment amount.
- The bot places buy/sell orders at each grid level and re-places orders as they fill, cycling profits through the grid.
- Risk limits cap total capital, per-coin exposure, and daily losses.
- On restart, `trading/recovery.py` reconciles live order state from CoinDCX and resumes all active grids automatically.

## Stack

- **Python** (asyncio) — `python-telegram-bot`, `httpx`, `aiosqlite`
- **SQLite** — local database at `data/grid_bot.db` (all state, no external DB)
- **CoinDCX REST API** — order placement and status
- **Telegram Bot API** — entire user interface

## Project layout

```
grid-trading-bot/
├── main.py                  # Entrypoint — wires everything together
├── config/settings.py       # Loads all config from env vars
├── bot_telegram/            # Telegram command handlers, keyboards, formatters
├── trading/                 # Core engine: DCA manager, order monitor, price monitor, recovery
├── exchange/                # CoinDCX API client (+ paper exchange stub)
├── grid/                    # Grid price generation (arithmetic/geometric)
├── risk/                    # Risk manager (capital limits, daily loss halts)
├── storage/                 # SQLite database, models, repositories
├── notifications/           # Telegram notifier wrapper
├── tests/                   # pytest suite (no live API or Telegram needed)
└── requirements.txt
```

## Running the bot

The bot is **not currently configured to run** — it needs credentials first.

### Required secrets (set as Replit Secrets or in a `.env` file)

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram user ID (from @userinfobot) |
| `COINDCX_API_KEY` | From the CoinDCX API settings page |
| `COINDCX_API_SECRET` | From the CoinDCX API settings page |

### Optional configuration (with defaults)

See `grid-trading-bot/.env.example` for the full list of tunable parameters (risk limits, poll intervals, log level, etc.).

### Start command

```bash
cd grid-trading-bot && python main.py
```

### Running tests

```bash
cd grid-trading-bot && python -m pytest tests/ -v
```

## Important notes

- **This bot places real orders with real money** once configured with live CoinDCX credentials.
- There is no paper-trading / simulation mode.
- Only Telegram user IDs listed in `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_USER_IDS` can control the bot.

## User preferences

*(none recorded yet)*
