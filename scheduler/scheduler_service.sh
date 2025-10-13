#!/bin/bash
# VK Ads Manager Scheduler - Linux/macOS startup script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SCHEDULER_SCRIPT="$SCRIPT_DIR/scheduler_main.py"
PID_FILE="$SCRIPT_DIR/scheduler.pid"
LOG_FILE="$SCRIPT_DIR/scheduler_startup.log"

# Функция для логирования
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Проверка статуса
status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log "Scheduler запущен (PID: $PID)"
            return 0
        else
            log "PID файл существует, но процесс не найден"
            rm -f "$PID_FILE"
        fi
    fi
    log "Scheduler не запущен"
    return 1
}

# Запуск планировщика
start() {
    if status > /dev/null; then
        log "Scheduler уже запущен"
        return 1
    fi
    
    log "Запуск VK Ads Manager Scheduler..."
    cd "$PROJECT_DIR"
    
    nohup python3 "$SCHEDULER_SCRIPT" > "$SCRIPT_DIR/scheduler_output.log" 2>&1 &
    echo $! > "$PID_FILE"
    
    sleep 2
    if status > /dev/null; then
        log "Scheduler успешно запущен"
        return 0
    else
        log "Ошибка запуска Scheduler"
        return 1
    fi
}

# Остановка планировщика
stop() {
    if ! status > /dev/null; then
        log "Scheduler не запущен"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    log "Остановка Scheduler (PID: $PID)..."
    
    kill -TERM "$PID"
    
    # Ждем graceful shutdown
    for i in {1..30}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Принудительное завершение если не остановился
    if ps -p "$PID" > /dev/null 2>&1; then
        log "Принудительное завершение процесса"
        kill -KILL "$PID"
    fi
    
    rm -f "$PID_FILE"
    log "Scheduler остановлен"
}

# Перезапуск
restart() {
    stop
    sleep 2
    start
}

# Показ логов
logs() {
    if [ -f "$SCRIPT_DIR/scheduler_output.log" ]; then
        tail -f "$SCRIPT_DIR/scheduler_output.log"
    else
        echo "Лог файл не найден"
        return 1
    fi
}

# Основная логика
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start   - Запуск планировщика"
        echo "  stop    - Остановка планировщика"
        echo "  restart - Перезапуск планировщика"
        echo "  status  - Проверка статуса"
        echo "  logs    - Показать логи (Ctrl+C для выхода)"
        exit 1
        ;;
esac

exit $?