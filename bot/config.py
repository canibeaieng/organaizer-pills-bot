from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(slots=True)
class Settings:
    bot_token: str
    timezone: ZoneInfo



def _read_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())



def load_settings() -> Settings:
    _read_env_file()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана")

    timezone_name = os.getenv("BOT_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
    return Settings(bot_token=token, timezone=ZoneInfo(timezone_name))
