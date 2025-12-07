import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logging():
    # Путь относительно корня проекта
    project_root = Path(__file__).parent.parent
    log_dir = project_root / "logs"
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("vk_ads_manager")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"vk_ads_manager_{timestamp}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info(f"📝 Логирование в файл: {log_file}")
    return logger
