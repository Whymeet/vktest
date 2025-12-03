"""
Веб-админ панель для управления VK Ads Manager
Позволяет настраивать конфигурацию через веб-интерфейс
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json
import os
import subprocess
import sys
import signal
import re
import atexit
from datetime import datetime
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__)
app.secret_key = 'vk-ads-manager-secret-key-2024'  # Измените на свой секретный ключ

CONFIG_PATH = os.path.join("cfg", "config.json")
SCHEDULER_SCRIPT = os.path.join("scheduler", "scheduler_main.py")
MAIN_SCRIPT = os.path.join("src", "main.py")

# Глобальная переменная для отслеживания запущенных процессов
running_processes = {
    'scheduler': None,
    'analysis': None
}

def kill_all_scheduler_processes():
    """Останавливает ВСЕ процессы scheduler_main.py и main.py (даже запущенные вне админ панели)"""
    if sys.platform == 'win32':
        try:
            # Находим все процессы scheduler_main.py
            result = subprocess.run(
                ['wmic', 'process', 'where', "commandline like '%scheduler_main.py%'", 'get', 'processid'],
                capture_output=True, text=True, timeout=5
            )
            pids = [line.strip() for line in result.stdout.split('\n')[1:] if line.strip().isdigit()]
            
            for pid in pids:
                print(f"   Останавливаю scheduler_main.py (PID: {pid})...")
                subprocess.run(['taskkill', '/F', '/T', '/PID', pid], capture_output=True, timeout=5)
            
            # Находим все процессы main.py
            result = subprocess.run(
                ['wmic', 'process', 'where', "commandline like '%main.py%' and not commandline like '%scheduler_main.py%'", 'get', 'processid'],
                capture_output=True, text=True, timeout=5
            )
            pids = [line.strip() for line in result.stdout.split('\n')[1:] if line.strip().isdigit()]
            
            for pid in pids:
                print(f"   Останавливаю main.py (PID: {pid})...")
                subprocess.run(['taskkill', '/F', '/T', '/PID', pid], capture_output=True, timeout=5)
                
        except Exception as e:
            print(f"   ⚠️ Ошибка при поиске процессов: {e}")
    else:
        # Linux/Mac: используем pkill
        try:
            subprocess.run(['pkill', '-f', 'scheduler_main.py'], timeout=5)
            subprocess.run(['pkill', '-f', 'main.py'], timeout=5)
        except Exception as e:
            print(f"   ⚠️ Ошибка при остановке процессов: {e}")

def cleanup_processes():
    """Остановка всех запущенных процессов при завершении программы"""
    print("\n🛑 Останавливаю все запущенные процессы...")
    
    # Сначала останавливаем процессы из running_processes
    for process_name, process in running_processes.items():
        if process is not None and process.poll() is None:
            try:
                print(f"   Останавливаю {process_name} (PID: {process.pid})...")
                if sys.platform == 'win32':
                    # Windows: используем taskkill для гарантированного завершения
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], 
                                 capture_output=True, timeout=5)
                else:
                    # Linux/Mac: отправляем SIGTERM, затем SIGKILL
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                
                print(f"   ✅ {process_name} остановлен")
            except Exception as e:
                print(f"   ⚠️ Ошибка при остановке {process_name}: {e}")
    
    # Затем ищем и останавливаем ВСЕ оставшиеся процессы scheduler/analysis
    print("   🔍 Поиск других процессов scheduler_main.py и main.py...")
    kill_all_scheduler_processes()
    
    running_processes['scheduler'] = None
    running_processes['analysis'] = None
    print("✅ Все процессы завершены\n")

# Регистрируем функцию очистки при выходе
atexit.register(cleanup_processes)

# Обработчик сигналов для корректного завершения
def signal_handler(signum, frame):
    """Обработчик сигналов завершения"""
    print("\n🛑 Получен сигнал завершения...")
    cleanup_processes()
    sys.exit(0)

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Terminate
if sys.platform == 'win32':
    signal.signal(signal.SIGBREAK, signal_handler)  # Ctrl+Break на Windows

def load_config():
    """Загружает конфигурацию из файла"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "vk_ads_api": {
                "base_url": "https://ads.vk.com/api/v2",
                "accounts": {}
            },
            "analysis_settings": {
                "lookback_days": 10,
                "spent_limit_rub": 100.0,
                "dry_run": False,
                "sleep_between_calls": 0.25
            },
            "statistics_trigger": {
                "enabled": False,
                "wait_seconds": 10,
                "description": "Настройки триггера обновления статистики VK"
            },
            "telegram": {
                "bot_token": "",
                "chat_id": "",
                "enabled": False
            },
            "scheduler": {
                "enabled": True,
                "interval_minutes": 1,
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
        }

def save_config(config):
    """Сохраняет конфигурацию в файл"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    """Главная страница - дашборд"""
    config = load_config()
    accounts_count = len(config.get("vk_ads_api", {}).get("accounts", {}))
    
    return render_template('dashboard.html', 
                         config=config,
                         accounts_count=accounts_count)

@app.route('/accounts')
def accounts():
    """Страница управления кабинетами VK Ads"""
    config = load_config()
    accounts = config.get("vk_ads_api", {}).get("accounts", {})
    return render_template('accounts.html', accounts=accounts)

@app.route('/accounts/add', methods=['POST'])
def add_account():
    """Добавление нового кабинета"""
    config = load_config()
    
    account_name = request.form.get('account_name')
    api_token = request.form.get('api_token')
    trigger_id = request.form.get('trigger_id', '')
    spent_limit = request.form.get('spent_limit', '')
    
    if not account_name or not api_token:
        flash('Название кабинета и API токен обязательны!', 'error')
        return redirect(url_for('accounts'))
    
    # Создаем структуру кабинета
    account_data = {
        "api": api_token
    }
    
    if trigger_id:
        try:
            account_data["trigger"] = int(trigger_id)
        except ValueError:
            flash('ID триггера должен быть числом!', 'error')
            return redirect(url_for('accounts'))
    
    if spent_limit:
        try:
            account_data["spent_limit_rub"] = float(spent_limit)
        except ValueError:
            flash('Лимит расходов должен быть числом!', 'error')
            return redirect(url_for('accounts'))
    
    # Добавляем кабинет в конфигурацию
    if "vk_ads_api" not in config:
        config["vk_ads_api"] = {"base_url": "https://ads.vk.com/api/v2", "accounts": {}}
    
    config["vk_ads_api"]["accounts"][account_name] = account_data
    save_config(config)
    
    flash(f'Кабинет "{account_name}" успешно добавлен!', 'success')
    return redirect(url_for('accounts'))

@app.route('/accounts/edit/<account_name>', methods=['GET', 'POST'])
def edit_account(account_name):
    """Редактирование кабинета"""
    config = load_config()
    accounts = config.get("vk_ads_api", {}).get("accounts", {})
    
    if account_name not in accounts:
        flash(f'Кабинет "{account_name}" не найден!', 'error')
        return redirect(url_for('accounts'))
    
    if request.method == 'POST':
        new_name = request.form.get('account_name')
        api_token = request.form.get('api_token')
        trigger_id = request.form.get('trigger_id', '')
        spent_limit = request.form.get('spent_limit', '')
        
        if not new_name or not api_token:
            flash('Название кабинета и API токен обязательны!', 'error')
            return redirect(url_for('edit_account', account_name=account_name))
        
        # Обновляем данные кабинета
        account_data = {"api": api_token}
        
        if trigger_id:
            try:
                account_data["trigger"] = int(trigger_id)
            except ValueError:
                flash('ID триггера должен быть числом!', 'error')
                return redirect(url_for('edit_account', account_name=account_name))
        
        if spent_limit:
            try:
                account_data["spent_limit_rub"] = float(spent_limit)
            except ValueError:
                flash('Лимит расходов должен быть числом!', 'error')
                return redirect(url_for('edit_account', account_name=account_name))
        
        # Если имя изменилось, удаляем старое и добавляем новое
        if new_name != account_name:
            del config["vk_ads_api"]["accounts"][account_name]
        
        config["vk_ads_api"]["accounts"][new_name] = account_data
        save_config(config)
        
        flash(f'Кабинет "{new_name}" успешно обновлен!', 'success')
        return redirect(url_for('accounts'))
    
    return render_template('edit_account.html', 
                         account_name=account_name,
                         account_data=accounts[account_name])

@app.route('/accounts/delete/<account_name>', methods=['POST'])
def delete_account(account_name):
    """Удаление кабинета"""
    config = load_config()
    
    if account_name in config.get("vk_ads_api", {}).get("accounts", {}):
        del config["vk_ads_api"]["accounts"][account_name]
        save_config(config)
        flash(f'Кабинет "{account_name}" успешно удален!', 'success')
    else:
        flash(f'Кабинет "{account_name}" не найден!', 'error')
    
    return redirect(url_for('accounts'))

@app.route('/settings')
def settings():
    """Страница общих настроек"""
    config = load_config()
    return render_template('settings.html', config=config)

@app.route('/settings/update', methods=['POST'])
def update_settings():
    """Обновление общих настроек"""
    config = load_config()
    
    try:
        # Настройки анализа
        config["analysis_settings"]["lookback_days"] = int(request.form.get('lookback_days', 10))
        config["analysis_settings"]["spent_limit_rub"] = float(request.form.get('spent_limit_rub', 100.0))
        config["analysis_settings"]["dry_run"] = request.form.get('dry_run') == 'on'
        config["analysis_settings"]["sleep_between_calls"] = float(request.form.get('sleep_between_calls', 0.25))
        
        # Telegram настройки
        config["telegram"]["bot_token"] = request.form.get('telegram_bot_token', '')
        config["telegram"]["chat_id"] = request.form.get('telegram_chat_id', '')
        config["telegram"]["enabled"] = request.form.get('telegram_enabled') == 'on'
        
        # Триггер статистики
        config["statistics_trigger"]["enabled"] = request.form.get('statistics_trigger_enabled') == 'on'
        config["statistics_trigger"]["wait_seconds"] = int(request.form.get('statistics_trigger_wait_seconds', 10))
        
        # Планировщик
        config["scheduler"]["enabled"] = request.form.get('scheduler_enabled') == 'on'
        config["scheduler"]["interval_minutes"] = int(request.form.get('scheduler_interval_minutes', 1))
        config["scheduler"]["max_runs"] = int(request.form.get('scheduler_max_runs', 0))
        config["scheduler"]["start_delay_seconds"] = int(request.form.get('scheduler_start_delay_seconds', 10))
        config["scheduler"]["retry_on_error"] = request.form.get('scheduler_retry_on_error') == 'on'
        config["scheduler"]["retry_delay_minutes"] = int(request.form.get('scheduler_retry_delay_minutes', 5))
        config["scheduler"]["max_retries"] = int(request.form.get('scheduler_max_retries', 3))
        
        # Тихие часы
        config["scheduler"]["quiet_hours"]["enabled"] = request.form.get('quiet_hours_enabled') == 'on'
        config["scheduler"]["quiet_hours"]["start"] = request.form.get('quiet_hours_start', '23:00')
        config["scheduler"]["quiet_hours"]["end"] = request.form.get('quiet_hours_end', '08:00')
        
        save_config(config)
        flash('Настройки успешно обновлены!', 'success')
        
    except ValueError as e:
        flash(f'Ошибка в значениях настроек: {e}', 'error')
    
    return redirect(url_for('settings'))

@app.route('/api/config')
def api_config():
    """API endpoint для получения конфигурации"""
    config = load_config()
    return jsonify(config)

@app.route('/logs')
def logs():
    """Страница просмотра логов"""
    log_dir = "logs"
    log_files = []
    
    if os.path.exists(log_dir):
        files = sorted(os.listdir(log_dir), reverse=True)
        for filename in files[:10]:  # Показываем последние 10 файлов
            filepath = os.path.join(log_dir, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                log_files.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%d.%m.%Y %H:%M:%S')
                })
    
    return render_template('logs.html', log_files=log_files)

@app.route('/logs/view/<filename>')
def view_log(filename):
    """Просмотр содержимого лог-файла"""
    log_path = os.path.join("logs", filename)
    
    if not os.path.exists(log_path):
        flash('Файл не найден!', 'error')
        return redirect(url_for('logs'))
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template('view_log.html', filename=filename, content=content)
    except Exception as e:
        flash(f'Ошибка чтения файла: {e}', 'error')
        return redirect(url_for('logs'))

@app.route('/control')
def control():
    """Страница управления процессами"""
    config = load_config()
    
    # Проверяем статус процессов
    scheduler_running = running_processes['scheduler'] is not None and running_processes['scheduler'].poll() is None
    analysis_running = running_processes['analysis'] is not None and running_processes['analysis'].poll() is None
    
    return render_template('control.html', 
                         config=config,
                         scheduler_running=scheduler_running,
                         analysis_running=analysis_running)

@app.route('/control/start_scheduler', methods=['POST'])
def start_scheduler():
    """Запуск планировщика"""
    global running_processes
    
    if running_processes['scheduler'] is not None and running_processes['scheduler'].poll() is None:
        flash('Планировщик уже запущен!', 'error')
        return redirect(url_for('control'))
    
    try:
        # Запускаем планировщик в отдельном процессе
        process = subprocess.Popen(
            [sys.executable, SCHEDULER_SCRIPT],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        running_processes['scheduler'] = process
        flash('✅ Планировщик успешно запущен!', 'success')
    except Exception as e:
        flash(f'❌ Ошибка запуска планировщика: {e}', 'error')
    
    return redirect(url_for('control'))

@app.route('/control/stop_scheduler', methods=['POST'])
def stop_scheduler():
    """Остановка планировщика"""
    global running_processes
    
    # Проверяем отслеживаемый процесс
    if running_processes['scheduler'] is not None and running_processes['scheduler'].poll() is None:
        try:
            # Останавливаем процесс с форсированным завершением дерева процессов
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(running_processes['scheduler'].pid)], 
                             capture_output=True, timeout=10)
            else:
                running_processes['scheduler'].terminate()
                try:
                    running_processes['scheduler'].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    running_processes['scheduler'].kill()
                    running_processes['scheduler'].wait()
            
            running_processes['scheduler'] = None
            flash('✅ Планировщик остановлен!', 'success')
        except Exception as e:
            flash(f'❌ Ошибка остановки планировщика: {e}', 'error')
    else:
        # Если в running_processes нет процесса, ищем все процессы scheduler
        try:
            print("🔍 Планировщик не найден в отслеживаемых процессах, ищу все экземпляры...")
            kill_all_scheduler_processes()
            flash('✅ Все процессы планировщика остановлены!', 'success')
        except Exception as e:
            flash(f'❌ Ошибка остановки планировщика: {e}', 'error')
    
    return redirect(url_for('control'))

@app.route('/control/start_analysis', methods=['POST'])
def start_analysis():
    """Запуск единичного анализа"""
    global running_processes
    
    if running_processes['analysis'] is not None and running_processes['analysis'].poll() is None:
        flash('Анализ уже выполняется!', 'error')
        return redirect(url_for('control'))
    
    try:
        # Запускаем основной скрипт
        process = subprocess.Popen(
            [sys.executable, MAIN_SCRIPT],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        running_processes['analysis'] = process
        flash('✅ Анализ запущен! Следите за логами.', 'success')
    except Exception as e:
        flash(f'❌ Ошибка запуска анализа: {e}', 'error')
    
    return redirect(url_for('control'))

@app.route('/control/stop_analysis', methods=['POST'])
def stop_analysis():
    """Остановка анализа"""
    global running_processes
    
    if running_processes['analysis'] is None or running_processes['analysis'].poll() is not None:
        flash('Анализ не запущен!', 'error')
        return redirect(url_for('control'))
    
    try:
        # Останавливаем процесс с форсированным завершением дерева процессов
        if sys.platform == 'win32':
            # Windows: используем taskkill с флагом /T для завершения дерева процессов
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(running_processes['analysis'].pid)], 
                         capture_output=True, timeout=10)
        else:
            # Linux/Mac: terminate, затем kill если не завершился
            running_processes['analysis'].terminate()
            try:
                running_processes['analysis'].wait(timeout=5)
            except subprocess.TimeoutExpired:
                running_processes['analysis'].kill()
                running_processes['analysis'].wait()
        
        running_processes['analysis'] = None
        flash('✅ Анализ остановлен!', 'success')
    except Exception as e:
        flash(f'❌ Ошибка остановки анализа: {e}', 'error')
    
    return redirect(url_for('control'))

@app.route('/control/kill_all', methods=['POST'])
def kill_all():
    """Остановка ВСЕХ процессов scheduler_main.py и main.py (даже запущенных вне админ панели)"""
    global running_processes
    
    try:
        print("🔥 ЭКСТРЕННАЯ ОСТАНОВКА ВСЕХ ПРОЦЕССОВ...")
        
        # Останавливаем отслеживаемые процессы
        for process_name, process in running_processes.items():
            if process is not None and process.poll() is None:
                try:
                    if sys.platform == 'win32':
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], 
                                     capture_output=True, timeout=5)
                    else:
                        process.kill()
                        process.wait()
                except:
                    pass
        
        # Останавливаем ВСЕ процессы scheduler/analysis
        kill_all_scheduler_processes()
        
        running_processes['scheduler'] = None
        running_processes['analysis'] = None
        
        flash('✅ Все процессы принудительно остановлены!', 'success')
    except Exception as e:
        flash(f'❌ Ошибка при остановке процессов: {e}', 'error')
    
    return redirect(url_for('control'))

@app.route('/control/status')
def control_status():
    """API endpoint для получения статуса процессов"""
    scheduler_running = running_processes['scheduler'] is not None and running_processes['scheduler'].poll() is None
    analysis_running = running_processes['analysis'] is not None and running_processes['analysis'].poll() is None
    
    return jsonify({
        'scheduler_running': scheduler_running,
        'analysis_running': analysis_running
    })

def parse_log_file(log_path):
    """Парсинг лог-файла для извлечения статистики"""
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        stats = {
            'accounts': {},
            'total_unprofitable': 0,
            'total_effective': 0,
            'total_testing': 0,
            'total_spent': 0.0,
            'total_goals': 0,
            'disabled_groups': [],
            'effective_groups': [],
            'testing_groups': [],
            'unprofitable_groups': []
        }
        
        current_account = None
        
        # Парсим построчно
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Определяем текущий кабинет
            if 'НАЧИНАЕМ АНАЛИЗ КАБИНЕТА:' in line:
                match = re.search(r'НАЧИНАЕМ АНАЛИЗ КАБИНЕТА:\s*(.+)', line)
                if match:
                    current_account = match.group(1).strip()
                    stats['accounts'][current_account] = {
                        'unprofitable': 0,
                        'effective': 0,
                        'testing': 0,
                        'total_groups': 0,
                        'spent': 0.0,
                        'goals': 0,
                        'limit': 0.0,
                        'unprofitable_groups': [],
                        'effective_groups': [],
                        'testing_groups': []
                    }
            
            # Лимит расходов для кабинета
            if current_account and 'Лимит расходов:' in line:
                match = re.search(r'Лимит расходов:\s*([\d.]+)₽', line)
                if match:
                    stats['accounts'][current_account]['limit'] = float(match.group(1))
            
            # Убыточная группа
            if current_account and 'УБЫТОЧНАЯ ГРУППА:' in line:
                match = re.search(r'\[(\d+)\]\s*(.+)', line)
                if match:
                    group_id = match.group(1)
                    group_name = match.group(2).strip()
                    # Ищем строку с расходами
                    if i + 1 < len(lines):
                        spent_line = lines[i + 1]
                        spent_match = re.search(r'Потрачено:\s*([\d.]+)₽', spent_line)
                        if spent_match:
                            spent = float(spent_match.group(1))
                            group_info = {
                                'id': group_id,
                                'name': group_name,
                                'spent': spent,
                                'account': current_account
                            }
                            stats['accounts'][current_account]['unprofitable_groups'].append(group_info)
                            stats['unprofitable_groups'].append(group_info)
            
            # Эффективная группа
            if current_account and 'ЭФФЕКТИВНАЯ ГРУППА:' in line:
                match = re.search(r'\[(\d+)\]\s*(.+)', line)
                if match:
                    group_id = match.group(1)
                    group_name = match.group(2).strip()
                    # Ищем строку с расходами и целями
                    if i + 1 < len(lines):
                        spent_line = lines[i + 1]
                        spent_match = re.search(r'Потрачено:\s*([\d.]+)₽.*?(\d+)\s*VK\s*целей', spent_line)
                        if spent_match:
                            spent = float(spent_match.group(1))
                            goals = int(spent_match.group(2))
                            group_info = {
                                'id': group_id,
                                'name': group_name,
                                'spent': spent,
                                'goals': goals,
                                'account': current_account
                            }
                            stats['accounts'][current_account]['effective_groups'].append(group_info)
                            stats['effective_groups'].append(group_info)
            
            # Тестируемая группа
            if current_account and 'ТЕСТИРУЕТСЯ:' in line:
                match = re.search(r'\[(\d+)\]\s*(.+)', line)
                if match:
                    group_id = match.group(1)
                    group_name = match.group(2).strip()
                    # Ищем строку с расходами
                    if i + 1 < len(lines):
                        spent_line = lines[i + 1]
                        spent_match = re.search(r'Потрачено:\s*([\d.]+)₽', spent_line)
                        if spent_match:
                            spent = float(spent_match.group(1))
                            group_info = {
                                'id': group_id,
                                'name': group_name,
                                'spent': spent,
                                'account': current_account
                            }
                            stats['accounts'][current_account]['testing_groups'].append(group_info)
                            stats['testing_groups'].append(group_info)
            
            # Итоговая статистика по кабинету
            if current_account and 'Убыточных групп' in line:
                match = re.search(r'Убыточных групп.*?:\s*(\d+)', line)
                if match:
                    stats['accounts'][current_account]['unprofitable'] = int(match.group(1))
            
            if current_account and 'Эффективных групп' in line:
                match = re.search(r'Эффективных групп.*?:\s*(\d+)', line)
                if match:
                    stats['accounts'][current_account]['effective'] = int(match.group(1))
            
            if current_account and 'Тестируемых/неактивных групп:' in line:
                match = re.search(r'Тестируемых/неактивных групп:\s*(\d+)', line)
                if match:
                    stats['accounts'][current_account]['testing'] = int(match.group(1))
            
            if current_account and 'Всего активных групп:' in line:
                match = re.search(r'Всего активных групп:\s*(\d+)', line)
                if match:
                    stats['accounts'][current_account]['total_groups'] = int(match.group(1))
            
            if current_account and 'Общие расходы за' in line:
                match = re.search(r'Общие расходы.*?:\s*([\d.]+)₽', line)
                if match:
                    stats['accounts'][current_account]['spent'] = float(match.group(1))
            
            if current_account and 'Общие VK цели за' in line:
                match = re.search(r'Общие VK цели.*?:\s*(\d+)', line)
                if match:
                    stats['accounts'][current_account]['goals'] = int(match.group(1))
            
            # Отключенные группы
            if 'Группа' in line and 'отключена' in line and '[DRY RUN]' not in line:
                match = re.search(r'Группа\s*(\d+)', line)
                if match:
                    group_id = match.group(1)
                    # Ищем эту группу в убыточных
                    for group in stats['unprofitable_groups']:
                        if group['id'] == group_id:
                            stats['disabled_groups'].append(group)
                            break
        
        # Считаем общую статистику
        for account_data in stats['accounts'].values():
            stats['total_unprofitable'] += account_data['unprofitable']
            stats['total_effective'] += account_data['effective']
            stats['total_testing'] += account_data['testing']
            stats['total_spent'] += account_data['spent']
            stats['total_goals'] += account_data['goals']
        
        return stats
    
    except Exception as e:
        print(f"Ошибка парсинга лога: {e}")
        return None

@app.route('/analytics')
def analytics():
    """Страница аналитики логов"""
    log_dir = Path("logs")
    
    # Находим последний лог-файл
    latest_log = None
    if log_dir.exists():
        log_files = sorted(log_dir.glob("vk_ads_manager_*.log"), reverse=True)
        if log_files:
            latest_log = log_files[0]
    
    stats = None
    log_filename = None
    
    if latest_log:
        log_filename = latest_log.name
        stats = parse_log_file(str(latest_log))
    
    return render_template('analytics.html', 
                         stats=stats,
                         log_filename=log_filename)

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 VK Ads Manager - Админ панель")
    print("=" * 60)
    print("📡 Сервер запущен на http://127.0.0.1:5000")
    print("🔧 Откройте браузер и перейдите по адресу выше")
    print("=" * 60)
    app.run(debug=True, host='127.0.0.1', port=5000)
