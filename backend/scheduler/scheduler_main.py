#!/usr/bin/env python3
"""
VK Ads Manager Scheduler - Автоматический планировщик анализа рекламных групп
Версия с PostgreSQL базой данных
Работает в несколько проходов:
1. Обычный анализ с настроенным lookback_days
2. Анализ с рандомной прибавкой к lookback_days
3. Автовключение ранее отключённых объявлений (если включено)
"""
import os
import sys
import time
import subprocess
import signal
import random
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Добавляем родительскую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from utils.time_utils import get_moscow_time
from utils.logging_setup import setup_logging, get_logger
from utils.vk_api import (
    get_banners_stats_day,
    get_banner_info,
    get_ad_group_full,
    get_campaign_full,
    toggle_banner_status,
    toggle_ad_group_status,
    toggle_campaign_status
)
from database import SessionLocal, init_db
from database import crud
from database.models import BannerAction, DisableRule

# Инициализация логирования
setup_logging()


def send_telegram_message(telegram_config: dict, message: str, logger) -> bool:
    """Отправка сообщения в Telegram"""
    if not telegram_config.get("enabled", False):
        return False
    
    bot_token = telegram_config.get("bot_token")
    chat_ids = telegram_config.get("chat_id", [])
    
    if not bot_token or not chat_ids:
        return False
    
    if isinstance(chat_ids, str):
        chat_ids = [chat_ids]
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    success_count = 0
    
    for chat_id in chat_ids:
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                success_count += 1
            else:
                logger.error(f"❌ Telegram ошибка для {chat_id}: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Telegram исключение для {chat_id}: {e}")
    
    return success_count > 0

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
        # Получаем user_id и username до настройки логирования
        self.user_id = os.environ.get('VK_ADS_USER_ID')
        self.username = os.environ.get('VK_ADS_USERNAME', 'unknown')

        self.setup_logging()
        self.load_settings()

        # Состояние планировщика
        self.is_running = False
        self.should_stop = False
        self.last_run_time = None
        self.next_run_time = None
        self.run_count = 0
        self.current_process = None
        self.last_reenable_time = None  # Время последнего автовключения

        # Обработка сигналов для graceful shutdown
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        self.logger.info("🔧 VK Ads Scheduler инициализирован")
        self.logger.info(f"👤 Пользователь: {self.username} (ID: {self.user_id})")
        self.logger.info(f"📂 Основной скрипт: {MAIN_SCRIPT}")

        # Логируем старт планировщика в отдельный файл событий
        self._log_scheduler_event("STARTED", "Планировщик запущен")

    def handle_signal(self, signum, frame):
        """Обработка сигналов для корректного завершения"""
        signal_names = {
            signal.SIGTERM: "SIGTERM",
            signal.SIGINT: "SIGINT",
            9: "SIGKILL"
        }
        signal_name = signal_names.get(signum, f"SIGNAL_{signum}")

        self.logger.warning(f"⚠️ Получен сигнал {signal_name} ({signum}), завершение работы...")
        self._log_scheduler_event("SIGNAL_RECEIVED", f"Получен сигнал {signal_name} ({signum})")

        self.should_stop = True
        if self.current_process:
            self.logger.warning(f"🛑 Остановка текущего процесса (PID: {self.current_process.pid})")
            self.current_process.terminate()
            self._log_scheduler_event("PROCESS_TERMINATED", f"Процесс {self.current_process.pid} остановлен")

    def setup_logging(self):
        """Настройка логирования с файлами по пользователям через loguru"""
        LOGS_DIR.mkdir(exist_ok=True)

        # Создаем директорию для логов планировщика
        scheduler_logs_dir = LOGS_DIR / "scheduler"
        scheduler_logs_dir.mkdir(exist_ok=True)

        # Используем loguru логгер с контекстом
        user_id_int = int(self.user_id) if self.user_id else None
        self.logger = get_logger(service="scheduler", function="auto_disable", user_id=user_id_int)

        timestamp = get_moscow_time().strftime("%Y%m%d")
        log_file = scheduler_logs_dir / f"scheduler_{self.username}_{timestamp}.log"
        self.logger.info(f"📝 Логирование в файл: {log_file}")

    def load_settings(self):
        """Загрузка настроек из БД для текущего пользователя"""
        # Get user_id from environment
        user_id = os.environ.get('VK_ADS_USER_ID')
        if not user_id:
            self.logger.warning("⚠️ VK_ADS_USER_ID not set, using defaults")
            return
        user_id = int(user_id)
        
        db = SessionLocal()
        try:
            settings = crud.get_user_setting(db, user_id, 'scheduler')
            if settings:
                self.settings = settings
                # Убедимся, что reenable настройки существуют
                if "reenable" not in self.settings:
                    self.settings["reenable"] = {
                        "enabled": False,
                        "interval_minutes": 120,  # Раз в 2 часа по умолчанию
                        "lookback_hours": 24,
                        "delay_after_analysis_seconds": 30,
                        "dry_run": True
                    }
                # Добавляем interval_minutes если его нет (для обратной совместимости)
                elif "interval_minutes" not in self.settings["reenable"]:
                    self.settings["reenable"]["interval_minutes"] = 120
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
                    },
                    "reenable": {
                        "enabled": False,
                        "interval_minutes": 120,  # Раз в 2 часа по умолчанию
                        "lookback_hours": 24,
                        "delay_after_analysis_seconds": 30,
                        "dry_run": True
                    }
                }
                # Сохраняем дефолтные настройки для этого пользователя
                crud.set_user_setting(db, user_id, 'scheduler', self.settings)
        finally:
            db.close()

    def reload_settings(self):
        """Перезагрузка настроек из БД"""
        self.load_settings()
        self.logger.debug("🔄 Настройки перезагружены")

    def _log_scheduler_event(self, event_type: str, message: str, extra_data: dict = None):
        """Логирование событий планировщика в отдельный файл для отслеживания"""
        try:
            scheduler_logs_dir = LOGS_DIR / "scheduler"
            events_file = scheduler_logs_dir / f"events_{self.username}.jsonl"

            event = {
                "timestamp": get_moscow_time().isoformat(),
                "username": self.username,
                "user_id": self.user_id,
                "event_type": event_type,
                "message": message,
                "run_count": self.run_count,
            }
            if extra_data:
                event.update(extra_data)

            with open(events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')

        except Exception as e:
            self.logger.error(f"❌ Ошибка записи события: {e}")

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
            self._log_scheduler_event("ANALYSIS_ERROR", "Скрипт не найден", {
                "run_type": run_type,
                "script_path": str(MAIN_SCRIPT)
            })
            return False

        extra_info = f" (+{extra_lookback_days} дней)" if extra_lookback_days > 0 else "..."

        self.logger.info(f"🚀 Запуск {run_type} анализа VK Ads Manager{extra_info}")
        self.logger.debug(f"   Команда: {sys.executable} {MAIN_SCRIPT}")
        self.logger.debug(f"   Рабочая директория: {PROJECT_ROOT}")
        if extra_lookback_days > 0:
            self.logger.debug(f"   VK_EXTRA_LOOKBACK_DAYS={extra_lookback_days}")

        # Логируем начало анализа
        self._log_scheduler_event("ANALYSIS_STARTED", f"Запуск {run_type} анализа", {
            "run_type": run_type,
            "extra_lookback_days": extra_lookback_days
        })

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

            process_pid = self.current_process.pid
            self.logger.debug(f"   PID процесса: {process_pid}")

            # Ждем завершения
            stdout, stderr = self.current_process.communicate()
            return_code = self.current_process.returncode
            elapsed = time.time() - start_time
            self.current_process = None

            # Сохраняем полные логи stdout и stderr в отдельные файлы
            self._save_process_logs(run_type, stdout, stderr, return_code, elapsed, extra_lookback_days)

            if return_code == 0:
                self.logger.info(f"✅ {run_type.capitalize()} анализ завершен успешно за {elapsed:.1f} сек")

                # Логируем stdout если есть важные сообщения
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    important_lines = []
                    for line in stdout_text.split('\n'):
                        if any(kw in line for kw in ['УБЫТОЧНОЕ', 'отключено', 'disabled', 'ERROR', 'ОШИБКА']):
                            important_lines.append(line.strip())
                            self.logger.info(f"   📋 {line.strip()}")

                    # Логируем успех в события
                    self._log_scheduler_event("ANALYSIS_SUCCESS", f"{run_type.capitalize()} анализ успешен", {
                        "run_type": run_type,
                        "elapsed_seconds": round(elapsed, 1),
                        "return_code": return_code,
                        "important_lines_count": len(important_lines),
                        "pid": process_pid
                    })
                return True
            else:
                # Определяем тип ошибки
                error_type = self._determine_error_type(return_code, stderr)

                self.logger.error(f"❌ {run_type.capitalize()} анализ завершен с ошибкой (код {return_code}) за {elapsed:.1f} сек")
                self.logger.error(f"   Тип ошибки: {error_type}")

                if stderr:
                    stderr_text = stderr.decode('utf-8', errors='ignore')
                    self.logger.error(f"Stderr (первые 2000 символов):\n{stderr_text[:2000]}")
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    # Показываем последние 50 строк stdout
                    lines = stdout_text.strip().split('\n')
                    last_lines = lines[-50:] if len(lines) > 50 else lines
                    self.logger.error(f"Stdout (последние {len(last_lines)} строк):\n" + '\n'.join(last_lines))

                # Логируем ошибку в события
                self._log_scheduler_event("ANALYSIS_FAILED", f"{run_type.capitalize()} анализ провален", {
                    "run_type": run_type,
                    "elapsed_seconds": round(elapsed, 1),
                    "return_code": return_code,
                    "error_type": error_type,
                    "pid": process_pid,
                    "stderr_preview": stderr.decode('utf-8', errors='ignore')[:500] if stderr else None
                })

                return False

        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска {run_type} анализа: {e}")
            import traceback
            error_trace = traceback.format_exc()
            self.logger.error(error_trace)

            # Логируем критическую ошибку
            self._log_scheduler_event("ANALYSIS_EXCEPTION", f"Исключение при запуске {run_type} анализа", {
                "run_type": run_type,
                "exception": str(e),
                "traceback": error_trace[:1000]
            })

            self.current_process = None
            return False

    def _determine_error_type(self, return_code: int, stderr: bytes) -> str:
        """Определение типа ошибки по коду возврата и stderr"""
        if return_code == -9 or return_code == 137:
            return "SIGKILL (вероятно OOM - нехватка памяти)"
        elif return_code == -15 or return_code == 143:
            return "SIGTERM (принудительное завершение)"
        elif return_code == -2 or return_code == 130:
            return "SIGINT (прерывание пользователем)"
        elif stderr:
            stderr_text = stderr.decode('utf-8', errors='ignore').lower()
            if 'memory' in stderr_text or 'oom' in stderr_text:
                return "Out of Memory (OOM)"
            elif 'timeout' in stderr_text:
                return "Timeout (превышено время выполнения)"
            elif 'connection' in stderr_text:
                return "Connection Error (ошибка подключения)"
            elif 'api' in stderr_text:
                return "API Error (ошибка API)"
            elif 'database' in stderr_text or 'postgres' in stderr_text:
                return "Database Error (ошибка БД)"

        return f"Unknown Error (код {return_code})"

    def _save_process_logs(self, run_type: str, stdout: bytes, stderr: bytes, return_code: int, elapsed: float, extra_days: int):
        """Сохранение полных логов процесса в отдельные файлы"""
        try:
            # Создаем директорию для логов процессов
            process_logs_dir = LOGS_DIR / "scheduler" / "process_logs" / self.username
            process_logs_dir.mkdir(parents=True, exist_ok=True)

            timestamp = get_moscow_time().strftime("%Y%m%d_%H%M%S")
            extra_suffix = f"_plus{extra_days}d" if extra_days > 0 else ""
            base_name = f"{timestamp}_{run_type}{extra_suffix}_rc{return_code}"

            # Сохраняем stdout
            if stdout:
                stdout_file = process_logs_dir / f"{base_name}_stdout.log"
                with open(stdout_file, 'wb') as f:
                    f.write(stdout)
                self.logger.debug(f"   📄 Stdout сохранён: {stdout_file}")

            # Сохраняем stderr (если есть)
            if stderr:
                stderr_file = process_logs_dir / f"{base_name}_stderr.log"
                with open(stderr_file, 'wb') as f:
                    f.write(stderr)
                self.logger.debug(f"   📄 Stderr сохранён: {stderr_file}")

            # Сохраняем метаданные
            meta_file = process_logs_dir / f"{base_name}_meta.txt"
            with open(meta_file, 'w', encoding='utf-8') as f:
                f.write(f"Пользователь: {self.username} (ID: {self.user_id})\n")
                f.write(f"Тип анализа: {run_type}\n")
                f.write(f"Дополнительные дни: {extra_days}\n")
                f.write(f"Код возврата: {return_code}\n")
                f.write(f"Время выполнения: {elapsed:.1f} сек\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Тип ошибки: {self._determine_error_type(return_code, stderr)}\n")

        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения логов процесса: {e}")

    def run_double_analysis(self):
        """Запуск двойного анализа: основной + со случайной прибавкой дней + автовключение (по интервалу)"""
        reenable_settings = self.settings.get("reenable", {})
        reenable_enabled = reenable_settings.get("enabled", False)
        reenable_interval = reenable_settings.get("interval_minutes", 120)
        
        # Проверяем, пора ли запускать автовключение
        should_run_reenable = False
        if reenable_enabled:
            if self.last_reenable_time is None:
                # Первый запуск - пропускаем автовключение, ждём следующего цикла
                should_run_reenable = False
                self.logger.info(f"📋 Автовключение: первый запуск, будет через {reenable_interval} мин")
            else:
                minutes_since_reenable = (get_moscow_time() - self.last_reenable_time).total_seconds() / 60
                if minutes_since_reenable >= reenable_interval:
                    should_run_reenable = True
                    self.logger.info(f"📋 Автовключение: прошло {minutes_since_reenable:.0f} мин (интервал {reenable_interval} мин) → ЗАПУСТИМ")
                else:
                    remaining = reenable_interval - minutes_since_reenable
                    self.logger.info(f"📋 Автовключение: осталось {remaining:.0f} мин до следующего запуска")
        
        total_passes = 3 if should_run_reenable else 2
        
        # 1-й проход: обычный анализ
        self.logger.info(f"🎯 ПРОХОД 1/{total_passes}: Стандартный анализ")
        success1 = self.run_analysis(extra_lookback_days=0, run_type="основной")
        
        if self.should_stop:
            return success1
        
        # Пауза между проходами (фиксированная 10 секунд)
        self.logger.info("⏳ Пауза 10 сек между проходами...")
        time.sleep(10)
        
        if self.should_stop:
            return success1
        
        # 2-й проход: с случайной прибавкой дней (5-30 дней) - ВЫПОЛНЯЕТСЯ ВСЕГДА
        extra_days = random.randint(5, 30)
        self.logger.info(f"🎯 ПРОХОД 2/{total_passes}: Расширенный анализ (+{extra_days} дней)")
        success2 = self.run_analysis(extra_lookback_days=extra_days, run_type="расширенный")
        
        if success1 and success2:
            self.logger.info("✅ Оба анализа завершены успешно!")
        elif success1:
            self.logger.warning("⚠️ Основной анализ успешен, расширенный неудачен")
        elif success2:
            self.logger.warning("⚠️ Расширенный анализ успешен, основной неудачен")
        else:
            self.logger.error("❌ Оба анализа неудачны")
        
        # 3-й проход: автовключение (только если прошёл интервал)
        if should_run_reenable and not self.should_stop:
            delay = reenable_settings.get("delay_after_analysis_seconds", 30)
            self.logger.info(f"⏳ Пауза {delay} сек перед автовключением...")
            time.sleep(delay)
            
            if not self.should_stop:
                self.logger.info(f"🎯 ПРОХОД 3/{total_passes}: Автовключение")
                self.run_reenable_analysis()
                # Обновляем время последнего автовключения
                self.last_reenable_time = get_moscow_time()
                self.logger.info(f"📋 Следующее автовключение через {reenable_interval} мин")
        
        # Инициализируем время для первого запуска (после первого цикла без автовключения)
        if reenable_enabled and self.last_reenable_time is None:
            self.last_reenable_time = get_moscow_time()
        
        return success1 or success2  # Успех если хотя бы один анализ прошел
    
    # ===== Автовключение отключённых объявлений =====
    
    def get_disabled_banners_for_period(self, db, lookback_hours: int, user_id: int) -> List[BannerAction]:
        """Получить отключённые баннеры за указанный период для конкретного пользователя"""
        from sqlalchemy import and_

        cutoff_time = get_moscow_time() - timedelta(hours=lookback_hours)

        query = db.query(BannerAction).filter(
            and_(
                BannerAction.user_id == user_id,
                BannerAction.action == 'disabled',
                BannerAction.created_at >= cutoff_time,
                BannerAction.is_dry_run == False
            )
        ).order_by(BannerAction.created_at.desc())
        
        all_actions = query.all()
        
        # Оставляем только уникальные banner_id
        seen_banners = set()
        unique_actions = []
        for action in all_actions:
            if action.banner_id not in seen_banners:
                seen_banners.add(action.banner_id)
                unique_actions.append(action)
        
        return unique_actions
    
    def get_fresh_stats(self, token: str, banner_id: int, lookback_days: int = 7, max_retries: int = 3) -> Optional[Dict]:
        """Получить свежую статистику для баннера из VK API с retry при rate limit"""
        base_url = "https://ads.vk.com/api/v2"
        
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        
        for attempt in range(max_retries):
            try:
                stats = get_banners_stats_day(
                    token=token,
                    base_url=base_url,
                    date_from=date_from,
                    date_to=date_to,
                    banner_ids=[banner_id],
                    metrics="base"
                )
                
                if stats:
                    for item in stats:
                        if item.get("id") == banner_id:
                            # Правильный парсинг: берём total.base для суммарной статистики
                            total = item.get("total", {}).get("base", {})
                            vk_data = total.get("vk", {}) if isinstance(total.get("vk"), dict) else {}
                            vk_goals = vk_data.get("goals", 0.0)
                            
                            return {
                                "spent": float(total.get("spent", 0.0)),
                                "clicks": float(total.get("clicks", 0.0)),
                                "shows": float(total.get("impressions", 0.0)),
                                "goals": float(vk_goals),
                                "vk_goals": float(vk_goals)
                            }
                
                return {"spent": 0, "clicks": 0, "shows": 0, "goals": 0, "vk_goals": 0}
                
            except Exception as e:
                error_str = str(e)
                # Проверяем на rate limit (HTTP 429)
                if "429" in error_str or "rate" in error_str.lower():
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                    self.logger.warning(f"⚠️ Rate limit для баннера {banner_id}, ждём {wait_time} сек (попытка {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"❌ Ошибка получения статистики для баннера {banner_id}: {e}")
                    return None
        
        self.logger.error(f"❌ Не удалось получить статистику для баннера {banner_id} после {max_retries} попыток")
        return None
    
    def should_reenable_banner(self, stats: Dict, rules: List[DisableRule]) -> bool:
        """Проверить, должен ли баннер быть включён обратно"""
        matched_rule = crud.check_banner_against_rules(stats, rules)
        return matched_rule is None
    
    def enable_banner_with_parents(self, token: str, banner_id: int, dry_run: bool = True) -> Dict:
        """Включить баннер вместе с группой и кампанией"""
        base_url = "https://ads.vk.com/api/v2"
        result = {"success": False, "banner_enabled": False, "group_enabled": False, "campaign_enabled": False, "error": None}
        
        if dry_run:
            self.logger.info(f"🧪 [DRY RUN] Баннер {banner_id} был бы включён")
            result["success"] = True
            result["dry_run"] = True
            return result
        
        try:
            # Получаем информацию о баннере
            banner_info = get_banner_info(token, base_url, banner_id)
            if not banner_info:
                result["error"] = f"Не удалось получить информацию о баннере {banner_id}"
                return result
            
            ad_group_id = banner_info.get("ad_group_id")
            if not ad_group_id:
                result["error"] = f"Баннер {banner_id} не содержит ad_group_id"
                return result
            
            # Получаем информацию о группе
            group_info = get_ad_group_full(token, base_url, ad_group_id)
            if not group_info:
                result["error"] = f"Не удалось получить информацию о группе {ad_group_id}"
                return result
            
            group_status = group_info.get("status")
            campaign_id = group_info.get("ad_plan_id")
            
            if not campaign_id:
                result["error"] = f"Группа {ad_group_id} не содержит ad_plan_id"
                return result
            
            # Получаем информацию о кампании
            campaign_info = get_campaign_full(token, base_url, campaign_id)
            if not campaign_info:
                result["error"] = f"Не удалось получить информацию о кампании {campaign_id}"
                return result
            
            campaign_status = campaign_info.get("status")
            
            # Включаем кампанию если выключена
            if campaign_status != "active":
                self.logger.info(f"   ⚠️ Кампания {campaign_id} выключена, включаем...")
                campaign_result = toggle_campaign_status(token, base_url, campaign_id, "active")
                if not campaign_result.get("success"):
                    result["error"] = f"Не удалось включить кампанию: {campaign_result.get('error')}"
                    return result
                result["campaign_enabled"] = True
            
            # Включаем группу если выключена
            if group_status != "active":
                self.logger.info(f"   ⚠️ Группа {ad_group_id} выключена, включаем...")
                group_result = toggle_ad_group_status(token, base_url, ad_group_id, "active")
                if not group_result.get("success"):
                    result["error"] = f"Не удалось включить группу: {group_result.get('error')}"
                    return result
                result["group_enabled"] = True
            
            # Включаем баннер
            banner_result = toggle_banner_status(token, base_url, banner_id, "active")
            if not banner_result.get("success"):
                result["error"] = f"Не удалось включить баннер: {banner_result.get('error')}"
                return result
            
            result["success"] = True
            result["banner_enabled"] = True
            return result
            
        except Exception as e:
            result["error"] = str(e)
            return result
    
    def run_reenable_analysis(self):
        """Запуск автовключения ранее отключённых объявлений"""
        reenable_settings = self.settings.get("reenable", {})
        lookback_hours = reenable_settings.get("lookback_hours", 24)
        dry_run = reenable_settings.get("dry_run", True)

        # Получаем user_id
        user_id = int(self.user_id) if self.user_id else None
        if not user_id:
            self.logger.error("❌ user_id не задан, автовключение невозможно")
            return

        db = SessionLocal()
        try:
            # Загружаем настройки анализа для получения lookback_days (пользовательские)
            analysis_settings = crud.get_user_setting(db, user_id, 'analysis_settings') or {}
            lookback_days = analysis_settings.get("lookback_days", 10)

            # Загружаем настройки Telegram (пользовательские)
            telegram_config = crud.get_user_setting(db, user_id, 'telegram') or {}

            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("🔄 АВТОВКЛЮЧЕНИЕ ОТКЛЮЧЁННЫХ ОБЪЯВЛЕНИЙ")
            self.logger.info("=" * 60)
            self.logger.info(f"   User ID: {user_id}")
            self.logger.info(f"   Период поиска отключённых: {lookback_hours} часов")
            self.logger.info(f"   Период статистики (lookback_days): {lookback_days} дней")
            self.logger.info(f"   Режим: {'🧪 DRY RUN (тестовый)' if dry_run else '🔴 РЕАЛЬНЫЙ'}")
            self.logger.info(f"   Telegram: {'✅ включён' if telegram_config.get('enabled') else '❌ выключен'}")

            # Получаем отключённые баннеры для этого пользователя
            disabled_banners = self.get_disabled_banners_for_period(db, lookback_hours, user_id)
            
            if not disabled_banners:
                self.logger.info("✅ Нет отключённых баннеров за указанный период")
                return
            
            self.logger.info(f"📋 Найдено {len(disabled_banners)} отключённых баннеров для проверки")

            # Получаем аккаунты пользователя
            accounts = crud.get_accounts(db, user_id=user_id)
            accounts_by_name = {acc.name: acc for acc in accounts}
            
            # Статистика
            total_checked = 0
            total_reenabled = 0
            total_skipped = 0
            total_errors = 0
            
            # Список включённых баннеров для Telegram
            reenabled_banners = []
            
            # Группируем по аккаунтам
            banners_by_account = {}
            for banner_action in disabled_banners:
                account_name = banner_action.account_name
                if account_name not in banners_by_account:
                    banners_by_account[account_name] = []
                banners_by_account[account_name].append(banner_action)
            
            for account_name, banner_actions in banners_by_account.items():
                if self.should_stop:
                    break
                    
                account = accounts_by_name.get(account_name)
                if not account:
                    self.logger.warning(f"⚠️ Аккаунт '{account_name}' не найден в БД")
                    continue
                
                # Получаем правила для аккаунта
                rules = crud.get_rules_for_account(db, account.id, enabled_only=True)
                if not rules:
                    self.logger.warning(f"⚠️ Нет активных правил для аккаунта '{account_name}', пропускаем")
                    continue
                
                self.logger.info("")
                self.logger.info(f"📁 Аккаунт: {account_name}")
                self.logger.info(f"   Баннеров для проверки: {len(banner_actions)}")
                self.logger.info(f"   Активных правил: {len(rules)}")
                
                api_token = account.api_token
                account_reenabled = 0
                
                for banner_action in banner_actions:
                    if self.should_stop:
                        break
                        
                    banner_id = banner_action.banner_id
                    banner_name = banner_action.banner_name or f"ID:{banner_id}"
                    total_checked += 1
                    
                    # Получаем свежую статистику за lookback_days из настроек анализа
                    fresh_stats = self.get_fresh_stats(api_token, banner_id, lookback_days)
                    
                    if fresh_stats is None:
                        self.logger.error(f"   ❌ [{banner_id}] Не удалось получить статистику")
                        total_errors += 1
                        continue
                    
                    # Логируем статистику
                    spent = fresh_stats.get('spent', 0)
                    goals = fresh_stats.get('goals', 0)
                    clicks = fresh_stats.get('clicks', 0)
                    
                    # Проверяем, можно ли включить
                    if self.should_reenable_banner(fresh_stats, rules):
                        self.logger.info(f"   ✅ [{banner_id}] {banner_name}")
                        self.logger.info(f"      Статистика: потрачено={spent:.2f}₽, целей={goals}, кликов={clicks}")
                        self.logger.info(f"      Не подпадает под правила → ВКЛЮЧАЕМ")
                        
                        enable_result = self.enable_banner_with_parents(api_token, banner_id, dry_run)
                        
                        if enable_result.get("success"):
                            total_reenabled += 1
                            account_reenabled += 1
                            
                            # Собираем данные для Telegram
                            reenabled_banners.append({
                                "account": account_name,
                                "banner_id": banner_id,
                                "banner_name": banner_name,
                                "spent": spent,
                                "goals": goals,
                                "clicks": clicks,
                                "campaign_enabled": enable_result.get("campaign_enabled", False),
                                "group_enabled": enable_result.get("group_enabled", False)
                            })
                            
                            if not dry_run:
                                crud.create_banner_action(
                                    db=db,
                                    user_id=account.user_id,  # ← добавлено
                                    banner_id=banner_id,
                                    action="enabled",
                                    account_name=account_name,
                                    banner_name=banner_action.banner_name,
                                    ad_group_id=banner_action.ad_group_id,
                                    spend=spent,
                                    clicks=clicks,
                                    shows=fresh_stats.get("shows", 0),
                                    conversions=goals,
                                    reason="Автовключение: статистика обновилась, правила не срабатывают",
                                    stats=fresh_stats,
                                    is_dry_run=dry_run
                                )
                                self.logger.info(f"      📝 Записано в историю")
                        else:
                            total_errors += 1
                            self.logger.error(f"      ❌ Ошибка включения: {enable_result.get('error')}")
                    else:
                        total_skipped += 1
                        self.logger.debug(f"   ⏭️ [{banner_id}] Всё ещё под правилами (spent={spent:.2f}, goals={goals})")
                    
                    # Rate limiting - 1 секунда между баннерами (VK API: max 35 req/sec)
                    time.sleep(1.0)
                
                if account_reenabled > 0:
                    self.logger.info(f"   📊 Итого по аккаунту: включено {account_reenabled} баннеров")
            
            # Итоги
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info(f"🏁 ИТОГИ АВТОВКЛЮЧЕНИЯ")
            self.logger.info(f"   Проверено баннеров: {total_checked}")
            self.logger.info(f"   Включено: {total_reenabled}")
            self.logger.info(f"   Пропущено (под правилами): {total_skipped}")
            self.logger.info(f"   Ошибок: {total_errors}")
            if dry_run:
                self.logger.info(f"   ⚠️ Режим DRY RUN - реальные изменения НЕ применялись")
            self.logger.info("=" * 60)
            
            # Отправляем уведомление в Telegram (ВСЕГДА, не только если есть включения)
            if telegram_config.get("enabled", False):
                self._send_reenable_telegram_notification(
                    telegram_config,
                    reenabled_banners,
                    total_checked,
                    total_reenabled,
                    total_skipped,
                    total_errors,
                    dry_run,
                    lookback_hours,
                    lookback_days
                )
            
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка автовключения: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            db.close()
    
    def _send_reenable_telegram_notification(
        self,
        telegram_config: dict,
        reenabled_banners: list,
        total_checked: int,
        total_reenabled: int,
        total_skipped: int,
        total_errors: int,
        dry_run: bool,
        lookback_hours: int,
        lookback_days: int
    ):
        """Отправка уведомления в Telegram о результатах автовключения"""
        try:
            mode_text = "🧪 ТЕСТОВЫЙ РЕЖИМ" if dry_run else "🔄 АВТОВКЛЮЧЕНИЕ"

            # Группируем баннеры по аккаунтам
            by_account = {}
            if reenabled_banners:
                for b in reenabled_banners:
                    acc = b["account"]
                    if acc not in by_account:
                        by_account[acc] = []
                    by_account[acc].append(b)

            # Если есть включённые баннеры - отправляем по кабинетам с тегами
            if by_account:
                for account_name, banners in by_account.items():
                    # Заменяем пробелы и спецсимволы в названии кабинета для тега
                    import re
                    clean_account_name = re.sub(r'[^\w]', '_', account_name)

                    # Формируем сообщение для каждого кабинета
                    message = f"<b>#включение_{clean_account_name}</b>\n\n"
                    message += f"<b>{mode_text}</b>\n\n"
                    message += f"📊 <b>Кабинет:</b> {account_name}\n"
                    message += f"• Отключённые за: последние {lookback_hours}ч\n"
                    message += f"• Статистика за: {lookback_days} дней\n"
                    message += f"• {'Было бы включено' if dry_run else 'Включено'}: <b>{len(banners)}</b>\n\n"

                    message += f"<b>{'Баннеры для включения:' if dry_run else 'Включённые баннеры:'}</b>\n"

                    for i, b in enumerate(banners[:10], 1):  # Ограничиваем 10 баннерами
                        extras = []
                        if b.get("campaign_enabled"):
                            extras.append("+ кампания")
                        if b.get("group_enabled"):
                            extras.append("+ группа")
                        extras_text = f" ({', '.join(extras)})" if extras else ""

                        message += f"{i}. {b['banner_name'][:25]}{extras_text}\n"
                        message += f"   💰 {b['spent']:.2f}₽ | 🎯 {b['goals']} целей\n"

                    if len(banners) > 10:
                        message += f"\n<i>... и ещё {len(banners) - 10} баннеров</i>\n"

                    if dry_run:
                        message += f"\n⚠️ <i>Для реального включения отключите DRY RUN в настройках</i>"

                    # Отправляем сообщение для этого кабинета
                    send_telegram_message(telegram_config, message, self.logger)
                    self.logger.info(f"📱 Telegram уведомление отправлено для кабинета: {account_name}")

            # Отправляем общее уведомление (всегда, даже если нет включений)
            summary_message = f"<b>{mode_text} - ИТОГИ</b>\n\n"
            summary_message += f"📊 <b>Результаты проверки:</b>\n"
            summary_message += f"• Отключённые за: последние {lookback_hours}ч\n"
            summary_message += f"• Статистика за: {lookback_days} дней\n"
            summary_message += f"• Проверено баннеров: {total_checked}\n"
            summary_message += f"• {'Было бы включено' if dry_run else 'Включено'}: <b>{total_reenabled}</b>\n"
            summary_message += f"• Пропущено (под правилами): {total_skipped}\n"
            summary_message += f"• Ошибок: {total_errors}\n"

            if total_reenabled == 0 and total_checked > 0:
                summary_message += f"\n✅ <i>Все проверенные баннеры остаются отключенными (подпадают под правила)</i>"
            elif total_checked == 0:
                summary_message += f"\nℹ️ <i>Нет отключённых баннеров за указанный период</i>"

            if dry_run and total_reenabled > 0:
                summary_message += f"\n⚠️ <i>Режим DRY RUN - реальные изменения НЕ применялись</i>"

            # Отправляем итоговое сообщение
            send_telegram_message(telegram_config, summary_message, self.logger)
            self.logger.info("📱 Telegram итоговое уведомление отправлено")

        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки Telegram: {e}")

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
        interval = self.settings.get('interval_minutes', 60)
        # Показываем интервал в удобном формате
        if interval < 1:
            interval_str = f"{interval * 60:.0f} сек"
        else:
            interval_str = f"{interval} мин"
        self.logger.info(f"   Интервал: {interval_str}")
        self.logger.info(f"   Макс. запусков: {max_runs if max_runs > 0 else 'без ограничений'}")
        self.logger.info("=" * 60)

        # Логируем начало цикла
        self._log_scheduler_event("SCHEDULER_LOOP_STARTED", "Основной цикл запущен", {
            "interval_minutes": self.settings.get('interval_minutes', 60),
            "max_runs": max_runs,
            "start_delay_seconds": start_delay
        })

        # Начальная задержка
        if start_delay > 0:
            self.logger.info(f"⏳ Начальная задержка {start_delay} сек...")
            time.sleep(start_delay)

        while not self.should_stop:
            # Перезагружаем настройки перед каждым запуском
            self.reload_settings()

            # Примечание: проверка settings.get("enabled") убрана
            # Теперь планировщик работает если он был запущен вручную,
            # независимо от настройки "enabled" в БД

            # Проверяем лимит запусков
            if max_runs > 0 and self.run_count >= max_runs:
                self.logger.info(f"🏁 Достигнут лимит запусков ({max_runs})")
                self._log_scheduler_event("MAX_RUNS_REACHED", f"Достигнут лимит запусков: {max_runs}")
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

                self._log_scheduler_event("RETRY_STARTED", f"Начало повторных попыток (макс: {max_retries})")

                for retry in range(1, max_retries + 1):
                    if self.should_stop:
                        break
                    self.logger.info(f"🔄 Повторная попытка {retry}/{max_retries} через {retry_delay} мин...")
                    time.sleep(retry_delay * 60)

                    if self.run_analysis():
                        self._log_scheduler_event("RETRY_SUCCESS", f"Успешная повторная попытка {retry}/{max_retries}")
                        break
                else:
                    self._log_scheduler_event("RETRY_FAILED", f"Все {max_retries} повторных попыток провалены")

            # Вычисляем следующий запуск
            self.calculate_next_run()
            self.logger.info(f"⏰ Следующий запуск: {self.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Ждем до следующего запуска
            self._sleep_until_next_run()

        self.is_running = False
        self.logger.warning("🛑 Планировщик остановлен")

        # Логируем остановку планировщика
        stop_reason = "disabled_by_user" if not self.settings.get("enabled", True) else (
            "max_runs_reached" if max_runs > 0 and self.run_count >= max_runs else
            "signal_received" if self.should_stop else "unknown"
        )
        self._log_scheduler_event("SCHEDULER_STOPPED", f"Планировщик остановлен. Причина: {stop_reason}", {
            "stop_reason": stop_reason,
            "total_runs": self.run_count,
            "was_forced": self.should_stop
        })

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
