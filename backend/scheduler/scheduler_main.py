#!/usr/bin/env python3
"""
VK Ads Manager Scheduler - Автоматический планировщик анализа рекламных групп
Версия с PostgreSQL базой данных
Работает в два прохода:
1. Обычный анализ с настроенным lookback_days
2. Анализ с рандомной прибавкой к lookback_days
"""
import os
import sys
import time
import subprocess
import logging
import signal
import random
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.time_utils import get_moscow_time
from database import SessionLocal, init_db
from database import crud

# Определяем окружение
IN_DOCKER = os.environ.get('IN_DOCKER', 'false').lower() == 'true'

if IN_DOCKER:
    PROJECT_ROOT = Path("/app")
    MAIN_SCRIPT = PROJECT_ROOT / "core" / "main.py"
    LOGS_DIR = PROJECT_ROOT / "logs"
else:
    PROJECT_ROOT = Path(__file__).parent.parent
    MAIN_SCRIPT = PROJECT_ROOT / "core" / "main.py"
    LOGS_DIR = PROJECT_ROOT / "logs"


class VKAdsScheduler:
    """Планировщик для автоматического запуска VK Ads Manager"""

    def __init__(self):
        """Инициализация планировщика"""
        self.setup_logging()
        self.load_settings()

        # Состояние планировщика
        self.is_running = False
        self.should_stop = False
        self.last_run_time = None
        self.next_run_time = None
        self.run_count = 0
        self.current_process = None

        # Обработка сигналов для graceful shutdown
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        self.logger.info("🔧 VK Ads Scheduler инициализирован")
        self.logger.info(f"📂 Основной скрипт: {MAIN_SCRIPT}")

    def handle_signal(self, signum, frame):
        """Обработка сигналов для корректного завершения"""
        self.logger.info(f"⚠️ Получен сигнал {signum}, завершение работы...")
        self.should_stop = True
        if self.current_process:
            self.current_process.terminate()

    def setup_logging(self):
        """Настройка логирования"""
        LOGS_DIR.mkdir(exist_ok=True)

        self.logger = logging.getLogger("vk_ads_scheduler")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Консольный хендлер
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Файловый хендлер
        log_file = LOGS_DIR / "scheduler.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def load_settings(self):
        """Загрузка настроек из БД"""
        db = SessionLocal()
        try:
            settings = crud.get_setting(db, 'scheduler')
            if settings:
                self.settings = settings
            else:
                # Дефолтные настройки
                self.settings = {
                    "enabled": True,
                    "interval_minutes": 60,
                    "max_runs": 0,
                    "start_delay_seconds": 10,
                    "retry_on_error": True,
                    "retry_delay_minutes": 5,
                    "max_retries": 3,
                    "quiet_hours": {
                        "enabled": False,
                        "start": "23:00",
                        "end": "08:00"
                    }
                }
                # Сохраняем дефолтные настройки
                crud.set_setting(db, 'scheduler', self.settings)
        finally:
            db.close()

    def reload_settings(self):
        """Перезагрузка настроек из БД"""
        self.load_settings()
        self.logger.debug("🔄 Настройки перезагружены")

    def is_quiet_hours(self):
        """Проверка тихих часов"""
        quiet_hours = self.settings.get("quiet_hours", {})
        if not quiet_hours.get("enabled", False):
            return False

        try:
            now = get_moscow_time()
            start = datetime.strptime(quiet_hours.get("start", "23:00"), "%H:%M").time()
            end = datetime.strptime(quiet_hours.get("end", "08:00"), "%H:%M").time()
            current_time = now.time()

            # Проверяем переход через полночь
            if start > end:
                return current_time >= start or current_time < end
            else:
                return start <= current_time < end
        except Exception as e:
            self.logger.error(f"Ошибка проверки тихих часов: {e}")
            return False

    def run_analysis(self, extra_lookback_days: int = 0, run_type: str = "основной"):
        """Запуск анализа объявлений
        
        Args:
            extra_lookback_days: Дополнительные дни к lookback_days (передаётся через переменную окружения)
            run_type: Тип запуска для логирования
        """
        if not MAIN_SCRIPT.exists():
            self.logger.error(f"❌ Скрипт не найден: {MAIN_SCRIPT}")
            return False

        extra_info = f" (+{extra_lookback_days} дней)" if extra_lookback_days > 0 else "..."
        
        self.logger.info(f"🚀 Запуск {run_type} анализа VK Ads Manager{extra_info}")
        self.logger.debug(f"   Команда: {sys.executable} {MAIN_SCRIPT}")
        self.logger.debug(f"   Рабочая директория: {PROJECT_ROOT}")
        if extra_lookback_days > 0:
            self.logger.debug(f"   VK_EXTRA_LOOKBACK_DAYS={extra_lookback_days}")

        try:
            start_time = time.time()
            
            # Подготавливаем окружение с дополнительными днями
            env = os.environ.copy()
            if extra_lookback_days > 0:
                env["VK_EXTRA_LOOKBACK_DAYS"] = str(extra_lookback_days)
            
            self.current_process = subprocess.Popen(
                [sys.executable, str(MAIN_SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
                env=env
            )

            # Ждем завершения
            stdout, stderr = self.current_process.communicate()
            return_code = self.current_process.returncode
            elapsed = time.time() - start_time
            self.current_process = None

            if return_code == 0:
                self.logger.info(f"✅ {run_type.capitalize()} анализ завершен успешно за {elapsed:.1f} сек")
                # Логируем stdout если есть важные сообщения
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    # Ищем ключевые строки в выводе
                    for line in stdout_text.split('\n'):
                        if any(kw in line for kw in ['УБЫТОЧНОЕ', 'отключено', 'disabled', 'ERROR', 'ОШИБКА']):
                            self.logger.info(f"   📋 {line.strip()}")
                return True
            else:
                self.logger.error(f"❌ {run_type.capitalize()} анализ завершен с ошибкой (код {return_code}) за {elapsed:.1f} сек")
                if stderr:
                    stderr_text = stderr.decode('utf-8', errors='ignore')
                    self.logger.error(f"Stderr:\n{stderr_text[:2000]}")
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    # Показываем последние 50 строк stdout
                    lines = stdout_text.strip().split('\n')
                    self.logger.error(f"Stdout (последние 50 строк):\n{'...'.join(lines[-50:])}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска {run_type} анализа: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.current_process = None
            return False

    def run_double_analysis(self):
        """Запуск двойного анализа: основной + со случайной прибавкой дней"""
        # 1-й проход: обычный анализ
        self.logger.info("🎯 ПРОХОД 1/2: Стандартный анализ")
        success1 = self.run_analysis(extra_lookback_days=0, run_type="основной")
        
        if self.should_stop:
            return success1
        
        # Пауза между проходами
        self.logger.info("⏳ Пауза 1 минута между проходами...")
        time.sleep(60)
        
        if self.should_stop:
            return success1
        
        # 2-й проход: с случайной прибавкой дней (5-30 дней) - ВЫПОЛНЯЕТСЯ ВСЕГДА
        extra_days = random.randint(5, 30)
        self.logger.info(f"🎯 ПРОХОД 2/2: Расширенный анализ (+{extra_days} дней)")
        success2 = self.run_analysis(extra_lookback_days=extra_days, run_type="расширенный")
        
        if success1 and success2:
            self.logger.info("✅ Оба прохода завершены успешно!")
        elif success1:
            self.logger.warning("⚠️ Основной анализ успешен, расширенный неудачен")
        elif success2:
            self.logger.warning("⚠️ Расширенный анализ успешен, основной неудачен")
        else:
            self.logger.error("❌ Оба прохода неудачны")
        
        return success1 or success2  # Успех если хотя бы один прошел

    def calculate_next_run(self):
        """Вычисление времени следующего запуска"""
        interval = self.settings.get("interval_minutes", 60)
        self.next_run_time = get_moscow_time() + timedelta(minutes=interval)
        return self.next_run_time

    def run(self):
        """Основной цикл планировщика"""
        self.is_running = True
        max_runs = self.settings.get("max_runs", 0)
        start_delay = self.settings.get("start_delay_seconds", 10)

        self.logger.info("=" * 60)
        self.logger.info("🕐 VK Ads Scheduler запущен")
        self.logger.info(f"   Интервал: {self.settings.get('interval_minutes', 60)} минут")
        self.logger.info(f"   Макс. запусков: {max_runs if max_runs > 0 else 'без ограничений'}")
        self.logger.info("=" * 60)

        # Начальная задержка
        if start_delay > 0:
            self.logger.info(f"⏳ Начальная задержка {start_delay} сек...")
            time.sleep(start_delay)

        while not self.should_stop:
            # Перезагружаем настройки перед каждым запуском
            self.reload_settings()

            # Проверяем лимит запусков
            if max_runs > 0 and self.run_count >= max_runs:
                self.logger.info(f"🏁 Достигнут лимит запусков ({max_runs})")
                break

            # Проверяем тихие часы
            if self.is_quiet_hours():
                self.logger.info("🌙 Тихие часы, пропуск запуска")
                self.calculate_next_run()
                self._sleep_until_next_run()
                continue

            # Запуск двойного анализа (2 прохода)
            self.run_count += 1
            self.last_run_time = get_moscow_time()
            self.logger.info(f"📊 Запуск #{self.run_count}")

            success = self.run_double_analysis()

            # Обработка ошибки с ретраями
            if not success and self.settings.get("retry_on_error", True):
                max_retries = self.settings.get("max_retries", 3)
                retry_delay = self.settings.get("retry_delay_minutes", 5)

                for retry in range(1, max_retries + 1):
                    if self.should_stop:
                        break
                    self.logger.info(f"🔄 Повторная попытка {retry}/{max_retries} через {retry_delay} мин...")
                    time.sleep(retry_delay * 60)

                    if self.run_analysis():
                        break

            # Вычисляем следующий запуск
            self.calculate_next_run()
            self.logger.info(f"⏰ Следующий запуск: {self.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Ждем до следующего запуска
            self._sleep_until_next_run()

        self.is_running = False
        self.logger.info("🛑 Планировщик остановлен")

    def _sleep_until_next_run(self):
        """Ожидание до следующего запуска с проверкой should_stop"""
        if not self.next_run_time:
            return

        while get_moscow_time() < self.next_run_time and not self.should_stop:
            time.sleep(1)


def main():
    """Точка входа"""
    print("=" * 60)
    print("🚀 VK Ads Manager Scheduler")
    print("   Версия с PostgreSQL")
    print("=" * 60)

    # Инициализация БД
    try:
        init_db()
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        sys.exit(1)

    # Запуск планировщика
    scheduler = VKAdsScheduler()

    try:
        scheduler.run()
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
