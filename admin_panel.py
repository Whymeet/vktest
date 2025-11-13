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
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'vk-ads-manager-secret-key-2024'  # Измените на свой секретный ключ

CONFIG_PATH = os.path.join("cfg", "config.json")
SCHEDULER_SCRIPT = os.path.join("scheduler", "scheduler_main.py")
MAIN_SCRIPT = "main.py"

# Глобальная переменная для отслеживания запущенных процессов
running_processes = {
    'scheduler': None,
    'analysis': None
}

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
    
    if running_processes['scheduler'] is None or running_processes['scheduler'].poll() is not None:
        flash('Планировщик не запущен!', 'error')
        return redirect(url_for('control'))
    
    try:
        # Останавливаем процесс
        if sys.platform == 'win32':
            running_processes['scheduler'].send_signal(signal.CTRL_BREAK_EVENT)
        else:
            running_processes['scheduler'].terminate()
        
        running_processes['scheduler'].wait(timeout=10)
        running_processes['scheduler'] = None
        flash('✅ Планировщик остановлен!', 'success')
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

@app.route('/control/status')
def control_status():
    """API endpoint для получения статуса процессов"""
    scheduler_running = running_processes['scheduler'] is not None and running_processes['scheduler'].poll() is None
    analysis_running = running_processes['analysis'] is not None and running_processes['analysis'].poll() is None
    
    return jsonify({
        'scheduler_running': scheduler_running,
        'analysis_running': analysis_running
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 VK Ads Manager - Админ панель")
    print("=" * 60)
    print("📡 Сервер запущен на http://127.0.0.1:5000")
    print("🔧 Откройте браузер и перейдите по адресу выше")
    print("=" * 60)
    app.run(debug=True, host='127.0.0.1', port=5000)
