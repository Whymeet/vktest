#!/usr/bin/env python3
"""
VK Ads Manager Scheduler - Автоматический планировщик анализа рекламных групп
Запускает основной анализатор через заданные интервалы времени
"""
import os
import sys
import time
import json
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта основных модулей
sys.path.insert(0, str(Path(__file__).parent.parent))


class VKAdsScheduler:
    """Планировщик для автоматического запуска VK Ads Manager"""
    
    def __init__(self, config_path=None):
        """Инициализация планировщика"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "cfg" / "config.json"
        
        self.config_path = Path(config_path)
        self.config = self.load_config()
        self.scheduler_config = self.config.get("scheduler", {})
        
        # Настройка логирования для планировщика
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # Создаем отдельный логгер для планировщика
        self.logger = logging.getLogger("vk_ads_scheduler")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', 
                                    datefmt='%Y-%m-%d %H:%M:%S')
        
        # Консольный хендлер
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Файловый хендлер
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"vk_ads_scheduler_{timestamp}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Путь к основному скрипту
        self.main_script_path = Path(__file__).parent.parent / "main.py"
        
        # Состояние планировщика
        self.is_running = False
        self.last_run_time = None
        self.next_run_time = None
        self.run_count = 0
        
        self.logger.info("🔧 VK Ads Scheduler инициализирован")
        self.logger.info(f"📂 Конфигурация: {self.config_path}")
        self.logger.info(f"📄 Основной скрипт: {self.main_script_path}")
    
    def load_config(self):
        """Загрузка конфигурации"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Добавляем дефолтные настройки планировщика если их нет
            if "scheduler" not in config:
                config["scheduler"] = {
                    "enabled": False,
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
                
                # Сохраняем обновленную конфигурацию
                self.save_config(config)
                
            return config
            
        except Exception as e:
            print(f"❌ Ошибка загрузки конфигурации: {e}")
            sys.exit(1)
    
    def save_config(self, config=None):
        """Сохранение конфигурации"""
        if config is None:
            config = self.config
            
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения конфигурации: {e}")
    
    def is_quiet_hours(self):
        """Проверка, находимся ли мы в тихих часах"""
        quiet_config = self.scheduler_config.get("quiet_hours", {})
        if not quiet_config.get("enabled", False):
            return False
            
        now = datetime.now()
        start_time = quiet_config.get("start", "23:00")
        end_time = quiet_config.get("end", "08:00")
        
        try:
            start_hour, start_minute = map(int, start_time.split(":"))
            end_hour, end_minute = map(int, end_time.split(":"))
            
            start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            
            # Если конечное время меньше начального, значит период переходит через полночь
            if end < start:
                end += timedelta(days=1)
                
            return start <= now <= end
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки тихих часов: {e}")
            return False
    
    def calculate_next_run_time(self):
        """Вычисление времени следующего запуска"""
        interval_minutes = self.scheduler_config.get("interval_minutes", 60)
        next_time = datetime.now() + timedelta(minutes=interval_minutes)
        
        # Если попадаем в тихие часы, переносим на окончание тихих часов
        if self.is_quiet_hours():
            quiet_config = self.scheduler_config.get("quiet_hours", {})
            end_time = quiet_config.get("end", "08:00")
            
            try:
                end_hour, end_minute = map(int, end_time.split(":"))
                tomorrow = datetime.now() + timedelta(days=1)
                next_time = tomorrow.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
                
                self.logger.info(f"🌙 Тихие часы активны, следующий запуск перенесен на {next_time.strftime('%d.%m.%Y %H:%M:%S')}")
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка расчета времени после тихих часов: {e}")
        
        return next_time
    
    def run_main_script(self):
        """Запуск основного скрипта анализа"""
        if not self.main_script_path.exists():
            self.logger.error(f"❌ Основной скрипт не найден: {self.main_script_path}")
            return False
            
        self.logger.info("🚀 Запуск анализа VK Ads Manager...")
        
        try:
            # Запускаем основной скрипт
            result = subprocess.run(
                [sys.executable, str(self.main_script_path)],
                cwd=str(self.main_script_path.parent),
                capture_output=True,
                text=True,
                timeout=1800  # 30 минут таймаут
            )
            
            if result.returncode == 0:
                self.logger.info("✅ Анализ завершен успешно")
                self.logger.debug(f"Вывод: {result.stdout}")
                return True
            else:
                self.logger.error(f"❌ Анализ завершился с ошибкой (код {result.returncode})")
                self.logger.error(f"Ошибка: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("❌ Анализ превысил таймаут (30 минут)")
            return False
        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска анализа: {e}")
            return False
    
    def run_with_retries(self):
        """Запуск с повторными попытками при ошибке"""
        max_retries = self.scheduler_config.get("max_retries", 3)
        retry_delay = self.scheduler_config.get("retry_delay_minutes", 5)
        retry_on_error = self.scheduler_config.get("retry_on_error", True)
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                if not retry_on_error:
                    self.logger.info("🔄 Повторные попытки отключены")
                    break
                    
                self.logger.info(f"🔄 Попытка {attempt + 1}/{max_retries + 1} через {retry_delay} минут...")
                time.sleep(retry_delay * 60)
            
            success = self.run_main_script()
            if success:
                if attempt > 0:
                    self.logger.info(f"✅ Анализ успешен с попытки {attempt + 1}")
                return True
        
        self.logger.error("❌ Все попытки запуска исчерпаны")
        return False
    
    def start(self):
        """Запуск планировщика"""
        if not self.scheduler_config.get("enabled", False):
            self.logger.error("❌ Планировщик отключен в конфигурации (scheduler.enabled = false)")
            return
            
        if self.is_running:
            self.logger.warning("⚠️ Планировщик уже запущен")
            return
            
        interval_minutes = self.scheduler_config.get("interval_minutes", 60)
        max_runs = self.scheduler_config.get("max_runs", 0)  # 0 = бесконечно
        start_delay = self.scheduler_config.get("start_delay_seconds", 10)
        
        self.logger.info("🎯 Запуск VK Ads Manager Scheduler")
        self.logger.info(f"⏰ Интервал: {interval_minutes} минут")
        self.logger.info(f"🔢 Максимум запусков: {'∞' if max_runs == 0 else max_runs}")
        self.logger.info(f"⏳ Задержка старта: {start_delay} секунд")
        
        if start_delay > 0:
            self.logger.info(f"⏳ Ожидание {start_delay} секунд перед первым запуском...")
            time.sleep(start_delay)
        
        self.is_running = True
        
        try:
            while self.is_running:
                # Проверяем лимит запусков
                if max_runs > 0 and self.run_count >= max_runs:
                    self.logger.info(f"🏁 Достигнут лимит запусков: {max_runs}")
                    break
                
                # Проверяем тихие часы
                if self.is_quiet_hours():
                    self.logger.info("🌙 Тихие часы, пропускаем запуск")
                    time.sleep(60)  # Проверяем каждую минуту
                    continue
                
                # Запускаем анализ
                self.run_count += 1
                self.last_run_time = datetime.now()
                
                self.logger.info(f"🔄 Запуск #{self.run_count} в {self.last_run_time.strftime('%d.%m.%Y %H:%M:%S')}")
                
                success = self.run_with_retries()
                
                # Вычисляем время следующего запуска
                self.next_run_time = self.calculate_next_run_time()
                
                self.logger.info(f"⏭️ Следующий запуск: {self.next_run_time.strftime('%d.%m.%Y %H:%M:%S')}")
                
                # Ждем до следующего запуска
                while datetime.now() < self.next_run_time and self.is_running:
                    time.sleep(60)  # Проверяем каждую минуту
                    
        except KeyboardInterrupt:
            self.logger.info("⏹️ Получен сигнал остановки")
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка планировщика: {e}")
        finally:
            self.is_running = False
            self.logger.info("🏁 Планировщик остановлен")
    
    def stop(self):
        """Остановка планировщика"""
        self.logger.info("⏹️ Остановка планировщика...")
        self.is_running = False
    
    def status(self):
        """Получение статуса планировщика"""
        status = {
            "running": self.is_running,
            "run_count": self.run_count,
            "last_run": self.last_run_time.isoformat() if self.last_run_time else None,
            "next_run": self.next_run_time.isoformat() if self.next_run_time else None,
            "config": self.scheduler_config
        }
        return status


def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="VK Ads Manager Scheduler")
    parser.add_argument("--config", help="Путь к файлу конфигурации")
    parser.add_argument("--status", action="store_true", help="Показать статус")
    
    args = parser.parse_args()
    
    scheduler = VKAdsScheduler(config_path=args.config)
    
    if args.status:
        status = scheduler.status()
        print(f"Статус: {'Запущен' if status['running'] else 'Остановлен'}")
        print(f"Запусков: {status['run_count']}")
        print(f"Последний запуск: {status['last_run'] or 'Никогда'}")
        print(f"Следующий запуск: {status['next_run'] or 'Не запланирован'}")
        return
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n⏹️ Остановка по Ctrl+C...")
        scheduler.stop()


if __name__ == "__main__":
    main()