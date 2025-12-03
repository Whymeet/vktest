# БЫСТРЫЕ ИСПРАВЛЕНИЯ ДЛЯ СЕРВЕРА

## 1. bot/telegram_bot.py 

**Строка ~31 - функция load_config():**
```python
# ЗАМЕНИТЬ:
    with open("cfg/config.json", "r", encoding="utf-8") as f:
    
# НА:
    config_path = Path(__file__).parent.parent / "cfg" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
```

**Строка ~110 - путь к файлу результатов:**
```python
# ЗАМЕНИТЬ:
    summary_file = Path(__file__).parent / "data" / "vk_summary_analysis.json"
    
# НА:
    summary_file = Path(__file__).parent.parent / "data" / "vk_summary_analysis.json"
```

## КОМАНДЫ:
```bash
cd /srv/vk-ads-parser/vktest
./scripts/stop.sh
nano bot/telegram_bot.py
# Применить исправления выше
./scripts/start.sh
```

После этого команда /info в боте заработает!