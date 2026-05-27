# German Learning Bot 🇩🇪

A Telegram bot for learning German via spaced repetition and daily practice questions. Features LLM-powered question generation (Anthropic Claude or local Ollama), a REST API mirror of all bot functionality, and one-command deployment to a Raspberry Pi.

## Features

- **Daily questions** — one question per user per day, sent automatically at a configured UTC hour
- **Spaced repetition learning** — weighted question selection that prioritises previously wrong answers
- **Multiple question types** — multiple choice, fill-in-the-blank, and reading comprehension
- **LLM question generation** — generate new questions via Anthropic Claude (with local Ollama fallback), then review and approve/reject candidates before they enter the bank
- **Question bank management** — browse, edit, and delete questions from within Telegram
- **Statistics** — per-user accuracy breakdown by category; downloadable as a file
- **REST API** — FastAPI service exposing the same engine for programmatic access
- **Automatic backup** — daily snapshot of the database

## Architecture

```
german_learning_bot/
├── bot/            # Telegram bot (python-telegram-bot)
│   └── handlers/   # One handler module per feature
├── api/            # FastAPI REST interface
│   └── routers/    # Mirrors bot features: learn, daily, stats, questions, backup
├── core/           # Business logic (no Telegram/HTTP dependencies)
│   ├── engine.py   # LearningEngine — single source of truth
│   ├── models.py   # Dataclasses: Question, UserStats, AnswerRecord, …
│   ├── question_bank.py  # Loads & manages questions.json
│   └── llm.py      # Anthropic + Ollama question generation
├── storage/
│   └── db.py       # TinyDB persistence layer
├── shared/
│   └── factory.py  # Builds the engine (used by both bot and API)
├── data/
│   └── questions.json  # Question bank (JSON)
└── config.py       # Settings loaded from environment variables
```

The `LearningEngine` in `core/` has no Telegram or HTTP imports — it can be driven by the bot, the API, or a CLI.

## Requirements

- Python 3.11+
- A [Telegram bot token](https://core.telegram.org/bots/tutorial) (`@BotFather`)
- **LLM (optional)** — either an `ANTHROPIC_API_KEY` or a running Ollama / LM Studio instance

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd german_learning_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file (or export variables) in the project root:

```env
TELEGRAM_BOT_TOKEN=your_token_here

# LLM — pick one or both (Anthropic takes priority when key is set)
ANTHROPIC_API_KEY=          # optional; leave blank to use local LLM
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=your-model-name

# Daily push hour in UTC (default: 7 = 9 AM CET)
DAILY_PUSH_HOUR_UTC=7
```

### 3. Run the bot

```bash
source .venv/bin/activate
python -m bot.main
```

### 4. Run the API (optional)

```bash
source .venv/bin/activate
python -m api.main
# or: uvicorn api.main:app --host 0.0.0.0 --port 8000
```

API docs are available at `http://localhost:8000/docs`.

## Bot commands

| Command | Description |
|---|---|
| `/start` | Register and show main menu |
| `/daily` | Get today's question |
| `/learn` | Practice with spaced repetition |
| `/stats` | Show your accuracy statistics |
| `/add` | Add a question manually |
| `/list` | Browse and edit the question bank |
| `/generate` | Generate new questions via LLM |
| `/candidates` | Review pending LLM-generated questions |

## REST API

All bot features are available over HTTP. Example endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/daily?user_id=1` | Get today's daily question |
| `POST` | `/daily/answer` | Submit daily answer |
| `GET` | `/learn?user_id=1` | Get next spaced-repetition question |
| `POST` | `/learn/answer` | Submit learn answer |
| `GET` | `/stats?user_id=1` | Get user statistics |
| `GET` | `/questions` | List all questions |
| `POST` | `/questions` | Add a question |
| `DELETE` | `/questions/{id}` | Delete a question |
| `POST` | `/backup` | Trigger a database backup |

Interactive docs: `GET /docs`

## Deployment to Raspberry Pi

`deploy.sh` syncs the project, installs dependencies, and registers a systemd service on a remote host. By default it connects as the current local user; override with `REMOTE_USER`.

```bash
# Deploy as current user
./deploy.sh

# Deploy as a specific user
REMOTE_USER=pi ./deploy.sh
```

The target host is `raspi5wifi.lan` (edit `REMOTE` in `deploy.sh` to change it). After deployment:

```bash
# On the Pi — create the .env file, then start the service
echo "TELEGRAM_BOT_TOKEN=your_token" > ~/projects/german_learning_bot/.env
sudo systemctl start german-bot

# Watch logs
sudo journalctl -fu german-bot
```

## Question bank format

`data/questions.json` contains two top-level keys:

```json
{
  "questions": [
    {
      "id": "unique-id",
      "cat": "vocabulary",
      "type": "mc",
      "difficulty": "A2",
      "q": "What does 'Hund' mean?",
      "opts": ["Dog", "Cat", "Bird", "Fish"],
      "answer": 0,
      "explanation": "'Hund' means dog in German."
    }
  ],
  "reading_passages": [
    {
      "id": "passage-1",
      "text": "Max geht jeden Tag in den Park…"
    }
  ]
}
```

**Question types:**

| `type` | `answer` value | Notes |
|---|---|---|
| `mc` | Integer index into `opts` | Multiple choice |
| `fill` | String | User types the answer |
| `reading` | Integer index into `opts` | Like `mc` but references a `passage_id` |

## Configuration reference

All settings are in `config.py` and read from environment variables:

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Telegram bot token |
| `ANTHROPIC_API_KEY` | `""` | Enables Claude; leave blank for local LLM |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model name |
| `OLLAMA_URL` | `http://macmini.lan:11434` | Local LLM endpoint |
| `OLLAMA_MODEL` | `huihui-qwen3.5-2b-abliterated-mlx` | Local model name |
| `DAILY_PUSH_HOUR_UTC` | `7` | Hour (UTC) for daily question push |
