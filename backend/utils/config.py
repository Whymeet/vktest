import json
import os
from pathlib import Path

def load_config():
    # Путь относительно корня проекта
    project_root = Path(__file__).parent.parent
    config_path = project_root / "cfg" / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError("❌ Файл cfg/config.json не найден! Создайте файл с настройками API.")
    except json.JSONDecodeError as e:
        raise ValueError(f"❌ Ошибка в cfg/config.json: {e}")
