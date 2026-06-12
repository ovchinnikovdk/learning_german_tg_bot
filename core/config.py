from __future__ import annotations

import os
from pathlib import Path


class _Settings:
    base_dir: Path = Path(__file__).parent
    data_dir: Path = base_dir / "data"

    @property
    def bot_token(self) -> str:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")
        return token

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db.json"

    @property
    def stats_backup_path(self) -> Path:
        return self.data_dir / "db_stats_backup.json"

    @property
    def questions_backup_path(self) -> Path:
        return self.data_dir / "db_questions_backup.json"

    @property
    def question_bank_path(self) -> Path:
        return self.data_dir / "questions.json"

    @property
    def ollama_url(self) -> str:
        return os.environ.get("OLLAMA_URL", "http://macmini.lan:11434")

    @property
    def ollama_model(self) -> str:
        return os.environ.get("OLLAMA_MODEL", "huihui-gemma-4-e2b-it-abliterated")

    @property
    def daily_push_hour_utc(self) -> int:
        """UTC hour for the 9am daily push (7 UTC = 9am CET, 8 UTC = 9am CEST)."""
        return int(os.environ.get("DAILY_PUSH_HOUR_UTC", "7"))


settings = _Settings()
